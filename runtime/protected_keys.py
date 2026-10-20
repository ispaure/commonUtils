"""Optional device-only 256-bit key adapters; namespaces are supplied by hosts."""
import base64


class KeyStoreUnavailable(ValueError):
    pass


def _bytes(value):
    return bytes(int(item) & 255 for item in value)


class AndroidKeys:
    def __init__(self, *, alias_prefix, aad_prefix):
        self.alias_prefix, self.aad_prefix = alias_prefix, aad_prefix
        from java import jclass
        self.jclass = jclass
        self.store = jclass('java.security.KeyStore').getInstance('AndroidKeyStore')
        self.store.load(None, None)

    def alias(self, identity):
        return self.alias_prefix + identity

    def create(self, identity, key):
        from java import jarray, jbyte
        String = self.jclass('java.lang.String')
        Properties = self.jclass('android.security.keystore.KeyProperties')
        Builder = self.jclass('android.security.keystore.KeyGenParameterSpec$Builder')
        specification = (Builder(self.alias(identity), Properties.PURPOSE_ENCRYPT | Properties.PURPOSE_DECRYPT)
                         .setBlockModes(jarray(String)(['GCM']))
                         .setEncryptionPaddings(jarray(String)(['NoPadding']))
                         .setKeySize(256).setRandomizedEncryptionRequired(True).build())
        generator = self.jclass('javax.crypto.KeyGenerator').getInstance('AES', 'AndroidKeyStore')
        generator.init(specification)
        native_key = generator.generateKey()
        cipher = self.jclass('javax.crypto.Cipher').getInstance('AES/GCM/NoPadding')
        cipher.init(1, native_key)
        aad = (self.aad_prefix + identity).encode()
        cipher.updateAAD(jarray(jbyte)([v if v < 128 else v - 256 for v in aad]))
        wrapped = cipher.doFinal(jarray(jbyte)([v if v < 128 else v - 256 for v in key]))
        return {'nonce': base64.b64encode(_bytes(cipher.getIV())).decode(),
                'wrapped': base64.b64encode(_bytes(wrapped)).decode()}

    def load(self, identity, record):
        from java import jarray, jbyte
        key = self.store.getKey(self.alias(identity), None)
        if key is None:
            raise KeyStoreUnavailable('The device encryption key is missing.')
        nonce = base64.b64decode(record['nonce'], validate=True)
        wrapped = base64.b64decode(record['wrapped'], validate=True)
        if len(nonce) != 12 or len(wrapped) != 48:
            raise KeyStoreUnavailable('Invalid protected-key record.')
        array = lambda data: jarray(jbyte)([v if v < 128 else v - 256 for v in data])
        cipher = self.jclass('javax.crypto.Cipher').getInstance('AES/GCM/NoPadding')
        cipher.init(2, key, self.jclass('javax.crypto.spec.GCMParameterSpec')(128, array(nonce)))
        cipher.updateAAD(array((self.aad_prefix + identity).encode()))
        return _bytes(cipher.doFinal(array(wrapped)))

    def delete(self, identity):
        self.store.deleteEntry(self.alias(identity))


class IOSKeys:
    """Security.framework generic-password item, unlocked/device-only, no sync."""
    def __init__(self, *, service, label, label_prefix):
        self.service, self.label, self.label_prefix = service, label, label_prefix
        import ctypes as c
        self.c = c
        self.security = c.CDLL('/System/Library/Frameworks/Security.framework/Security')
        self.cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        signatures = {
            'CFStringCreateWithCString': (c.c_void_p, [c.c_void_p, c.c_char_p, c.c_uint32]),
            'CFDataCreate': (c.c_void_p, [c.c_void_p, c.c_void_p, c.c_long]),
            'CFDataGetLength': (c.c_long, [c.c_void_p]),
            'CFDataGetBytePtr': (c.c_void_p, [c.c_void_p]),
            'CFDictionaryCreateMutable': (c.c_void_p, [c.c_void_p, c.c_long, c.c_void_p, c.c_void_p]),
            'CFDictionarySetValue': (None, [c.c_void_p, c.c_void_p, c.c_void_p]),
            'CFRelease': (None, [c.c_void_p]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.cf, name)
            function.restype, function.argtypes = result, arguments
        for name, arguments in {'SecItemAdd': [c.c_void_p, c.c_void_p],
                                'SecItemCopyMatching': [c.c_void_p, c.POINTER(c.c_void_p)],
                                'SecItemDelete': [c.c_void_p],
                                'SecItemUpdate': [c.c_void_p, c.c_void_p]}.items():
            function = getattr(self.security, name)
            function.restype, function.argtypes = c.c_int32, arguments

    def constant(self, name):
        library = self.cf if name.startswith('kCF') else self.security
        return self.c.c_void_p.in_dll(library, name).value

    def perform(self, operation, identity, key=None):
        c = self.c
        owned = []
        def string(value):
            pointer = self.cf.CFStringCreateWithCString(None, value.encode(), 0x08000100)
            owned.append(pointer)
            return pointer
        dictionary = self.cf.CFDictionaryCreateMutable(None, 0, None, None)
        owned.append(dictionary)
        def put(name, value):
            self.cf.CFDictionarySetValue(dictionary, self.constant(name), value)
        put('kSecClass', self.constant('kSecClassGenericPassword'))
        put('kSecAttrService', string(self.service))
        put('kSecAttrAccount', string(identity))
        put('kSecAttrSynchronizable', self.constant('kCFBooleanFalse'))
        result = c.c_void_p()
        try:
            if operation == 'create':
                put('kSecAttrLabel', string(self.label))
                put('kSecAttrAccessible', self.constant('kSecAttrAccessibleWhenUnlockedThisDeviceOnly'))
                buffer = c.create_string_buffer(key)
                data = self.cf.CFDataCreate(None, c.cast(buffer, c.c_void_p), len(key))
                owned.append(data)
                put('kSecValueData', data)
                status = self.security.SecItemAdd(dictionary, None)
            elif operation == 'load':
                put('kSecReturnData', self.constant('kCFBooleanTrue'))
                put('kSecMatchLimit', self.constant('kSecMatchLimitOne'))
                status = self.security.SecItemCopyMatching(dictionary, c.byref(result))
            elif operation == 'label':
                attributes = self.cf.CFDictionaryCreateMutable(None, 0, None, None)
                owned.append(attributes)
                self.cf.CFDictionarySetValue(attributes, self.constant('kSecAttrLabel'), string(self.label_prefix + key))
                status = self.security.SecItemUpdate(dictionary, attributes)
            else:
                status = self.security.SecItemDelete(dictionary)
            if operation == 'delete' and status == -25300:  # Already absent.
                return None
            if status:
                raise KeyStoreUnavailable('Could not access the device Keychain. Unlock the device and retry.')
            if operation == 'load':
                length = self.cf.CFDataGetLength(result)
                if length != 32:
                    raise KeyStoreUnavailable('Invalid device encryption key.')
                return c.string_at(self.cf.CFDataGetBytePtr(result), length)
            return None
        finally:
            if result.value:
                self.cf.CFRelease(result)
            for pointer in reversed(owned):
                self.cf.CFRelease(pointer)

    def create(self, identity, key):
        self.perform('create', identity, key)
        return {}

    def load(self, identity, record):
        return self.perform('load', identity)

    def delete(self, identity):
        self.perform('delete', identity)

    def set_label(self, identity, label):
        self.perform('label', identity, label)

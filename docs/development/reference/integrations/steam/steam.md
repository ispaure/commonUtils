# Steam launch detection

`is_linux_steam_big_picture()` checks whether the process was started through
Linux Steam Big Picture. It does not launch Steam or configure controllers.

```python
from commonUtils.integrations.steam import is_linux_steam_big_picture

if is_linux_steam_big_picture():
    print('Started through Steam Big Picture')
```

[Library overview](../../../overview.md).

"""Small raster icons are enlarged and centered independently of native style."""
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.tiles import TileDelegate


class Source(qt.QStandardItemModel):
    def item(self, index):
        return object()


class TileIconTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_tiny_portrait_landscape_and_square_icons_fill_a_centered_canvas(self):
        for style_name in qt.QStyleFactory.keys():
            view = qt.QListView()
            view.setStyle(qt.QStyleFactory.create(style_name))
            view.setIconSize(qt.QSize(100,140))
            view.folder_icon_size = qt.QSize(100,100)
            source = Source()
            proxy = qt.QIdentityProxyModel(view)
            proxy.setSourceModel(source)
            view.setModel(proxy)
            delegate = TileDelegate(view)
            for width, height in ((8,8),(8,16),(16,8)):
                original = qt.QPixmap(width,height)
                original.fill(qt.Qt.GlobalColor.red)
                source.clear()
                source.appendRow(qt.QStandardItem(qt.QIcon(original), 'Tiny icon'))
                option = qt.QStyleOptionViewItem()
                option.widget = view
                option.rect = qt.QRect(0,0,140,200)
                delegate.initStyleOption(option, proxy.index(0,0))
                pixmap = option.icon.pixmap(view.iconSize(), view.devicePixelRatioF())
                image = pixmap.toImage()
                points = [(x,y) for y in range(image.height()) for x in range(image.width())
                          if image.pixelColor(x,y).alpha() > 128]
                self.assertTrue(points)
                left, right = min(x for x,y in points), max(x for x,y in points)
                top, bottom = min(y for x,y in points), max(y for x,y in points)
                self.assertAlmostEqual((left+right)/2, (image.width()-1)/2, delta=1)
                self.assertAlmostEqual((top+bottom)/2, (image.height()-1)/2, delta=1)
                self.assertAlmostEqual((right-left+1)/(bottom-top+1), width/height, delta=.03)
                self.assertGreater(max(right-left+1,bottom-top+1), 90)
            view.deleteLater()

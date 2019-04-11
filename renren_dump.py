import sys
import spider
from spider_ui import Ui_Dialog, QtWidgets, QtGui


class SpiderDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.spider = spider.RenrenSpider()
        self.init_signals()
        if self.spider.is_login():
            self.ui.loginFrame.hide()
            self.ui.mainFrame.show()

    def init_signals(self):
        self.ui.loginBtn.clicked.connect(self.on_login)
        self.ui.startBtn.clicked.connect(self.on_start)
        self.ui.browserBtn.clicked.connect(self.on_browse_dir)

    def on_login(self):
        email = self.ui.emailInput.text()
        password = self.ui.passwordInput.text()
        remember = self.ui.rememberCkb.isChecked()
        icode = self.ui.iCodeInput.text()
        try:
            self.spider.login(email, password, icode, remember)
        except spider.iCodeRequired as e:
            self.show_icode()
            error = QtWidgets.QErrorMessage()
            error.showMessage(str(e))
        else:
            self.ui.loginFrame.hide()
            self.ui.mainFrame.show()

    def show_icode(self):
        with open('icode.jpg', 'wb') as f:
            f.write(self.spider.get_icode_image())
        icode_image = QtGui.QImage('icode.jpg')
        icode_pixmap = QtGui.QPixmap.fromImage(icode_image)
        self.ui.iCodeImg.setPixmap(icode_pixmap)
        self.ui.iCodeFrame.show()

    def on_start(self):
        self.spider.set_params(
            user_id=self.ui.userInput.text(),
            output_dir=self.ui.outputPathInput.text()
        )
        self.ui.progressFrame.show()
        self.spider.main(self)
        self.ui.label.setText("备份完成！")

    def on_browse_dir(self):
        file_dialog = QtWidgets.QFileDialog()
        file_dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        file_dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly)
        if file_dialog.exec_():
            self.ui.outputPathInput.setText(file_dialog.selectedFiles()[0])

    def progressbar(self, total: int, desc: str):
        ui = self.ui

        class ProgressBar(object):
            def __init__(self):
                self.current = 0.0
                ui.label.setText(desc)
                ui.progressBar.reset()

            def update(self, number: int = 1):
                self.current += number
                ui.progressBar.setValue(int(self.current / total * 100))

        return ProgressBar()


def main():
    app = QtWidgets.QApplication(sys.argv)
    dialog = SpiderDialog()
    dialog.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

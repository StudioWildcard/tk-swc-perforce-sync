# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'search_widget.ui'
#
#      by: pyside-uic 0.2.15 running on PySide 1.2.2
#
# WARNING! All changes made in this file will be lost!

from sgtk.platform.qt import QtCore
for name, cls in QtCore.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

from sgtk.platform.qt import QtGui
for name, cls in QtGui.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

class Ui_SearchWidget(object):
    def setupUi(self, SearchWidget):
        SearchWidget.setObjectName("SearchWidget")
        SearchWidget.resize(161, 50)
        self.horizontalLayout = QHBoxLayout(SearchWidget)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.group = QGroupBox(SearchWidget)
        self.group.setTitle("")
        self.group.setObjectName("group")
        self.horizontalLayout_2 = QHBoxLayout(self.group)
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setContentsMargins(4, 15, 4, 2)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.search = QLineEdit(self.group)
        self.search.setObjectName("search")
        self.horizontalLayout_2.addWidget(self.search)
        self.horizontalLayout.addWidget(self.group)

        self.retranslateUi(SearchWidget)
        QMetaObject.connectSlotsByName(SearchWidget)

    def get_query_text(self):
        return self.search.text()

    def retranslateUi(self, SearchWidget):
        SearchWidget.setWindowTitle(QApplication.translate("SearchWidget", "Form", None))
        self.search.setToolTip(QApplication.translate("SearchWidget", "Enter some text to filter the publishes shown in the view below.<br>\n"
"Click the magnifying glass icon above to disable the filter.", None))

from . import resources_rc

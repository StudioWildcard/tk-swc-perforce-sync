# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'dialog.ui'
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

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        # Dialog.resize(1226, 782)
        Dialog.resize(1500, 782)
        self.verticalLayout_5 = QVBoxLayout(Dialog)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.splitter = QSplitter(Dialog)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.splitter.sizePolicy().hasHeightForWidth())
        self.splitter.setSizePolicy(sizePolicy)
        self.splitter.setOrientation(Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.left_area_widget = QWidget(self.splitter)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.left_area_widget.sizePolicy().hasHeightForWidth())
        self.left_area_widget.setSizePolicy(sizePolicy)
        self.left_area_widget.setObjectName("left_area_widget")
        self.verticalLayout_2 = QVBoxLayout(self.left_area_widget)
        self.verticalLayout_2.setSpacing(2)
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")

        self.top_toolbar = QHBoxLayout()
        self.top_toolbar.setContentsMargins(0, 0, 0, 0)
        self.top_toolbar.setObjectName("top_toolbar")
        self.navigation_home = QToolButton(self.left_area_widget)
        self.navigation_home.setMinimumSize(QSize(40, 40))
        self.navigation_home.setMaximumSize(QSize(40, 40))
        self.navigation_home.setStyleSheet("QToolButton{\n"
"   border: none;\n"
"   background-color: none;\n"
"   background-repeat: no-repeat;\n"
"   background-position: center center;\n"
"   background-image: url(:/res/home.png);\n"
"}\n"
"\n"
"QToolButton:hover{\n"
"background-image: url(:/res/home_hover.png);\n"
"}\n"
"\n"
"QToolButton:Pressed {\n"
"background-image: url(:/res/home_pressed.png);\n"
"}\n"
"")
        self.navigation_home.setObjectName("navigation_home")
        self.top_toolbar.addWidget(self.navigation_home)
        self.navigation_prev = QToolButton(self.left_area_widget)
        self.navigation_prev.setMinimumSize(QSize(40, 40))
        self.navigation_prev.setMaximumSize(QSize(40, 40))
        self.navigation_prev.setStyleSheet("QToolButton{\n"
"   border: none;\n"
"   background-color: none;\n"
"   background-repeat: no-repeat;\n"
"   background-position: center center;\n"
"   background-image: url(:/res/left_arrow.png);\n"
"}\n"
"\n"
"QToolButton:disabled{\n"
"   background-image: url(:/res/left_arrow_disabled.png);\n"
"}\n"
"\n"
"QToolButton:hover{\n"
"background-image: url(:/res/left_arrow_hover.png);\n"
"}\n"
"\n"
"QToolButton:Pressed {\n"
"background-image: url(:/res/left_arrow_pressed.png);\n"
"}\n"
"")
        self.navigation_prev.setObjectName("navigation_prev")
        self.top_toolbar.addWidget(self.navigation_prev)
        self.navigation_next = QToolButton(self.left_area_widget)
        self.navigation_next.setMinimumSize(QSize(40, 40))
        self.navigation_next.setMaximumSize(QSize(40, 40))
        self.navigation_next.setStyleSheet("QToolButton{\n"
"   border: none;\n"
"   background-color: none;\n"
"   background-repeat: no-repeat;\n"
"   background-position: center center;\n"
"   background-image: url(:/res/right_arrow.png);\n"
"}\n"
"\n"
"QToolButton:disabled{\n"
"   background-image: url(:/res/right_arrow_disabled.png);\n"
"}\n"
"\n"
"\n"
"QToolButton:hover{\n"
"background-image: url(:/res/right_arrow_hover.png);\n"
"}\n"
"\n"
"QToolButton:Pressed {\n"
"background-image: url(:/res/right_arrow_pressed.png);\n"
"}\n"
"")
        self.navigation_next.setObjectName("navigation_next")
        self.top_toolbar.addWidget(self.navigation_next)
        self.label = QLabel(self.left_area_widget)
        self.label.setText("")
        self.label.setObjectName("label")
        self.top_toolbar.addWidget(self.label)
        self.verticalLayout_2.addLayout(self.top_toolbar)
        self.entity_preset_tabs = QTabWidget(self.left_area_widget)
        self.entity_preset_tabs.setMaximumSize(QSize(16777215, 16777202))
        self.entity_preset_tabs.setUsesScrollButtons(True)
        self.entity_preset_tabs.setObjectName("entity_preset_tabs")
        self.verticalLayout_2.addWidget(self.entity_preset_tabs)
        self.label_4 = QLabel(Dialog)
        self.label_4.setAlignment(Qt.AlignCenter)
        self.label_4.setObjectName("label_4")
        self.verticalLayout_2.addWidget(self.label_4)
        self.publish_type_list = QListView(self.left_area_widget)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.publish_type_list.sizePolicy().hasHeightForWidth())
        self.publish_type_list.setSizePolicy(sizePolicy)
        self.publish_type_list.setMinimumSize(QSize(300, 300))
        self.publish_type_list.setStyleSheet("QListView::item {\n"
"    border-top: 1px dotted #888888;\n"
"    padding: 5px;\n"
" }")
        self.publish_type_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.publish_type_list.setProperty("showDropIndicator", False)
        self.publish_type_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.publish_type_list.setUniformItemSizes(True)
        self.publish_type_list.setObjectName("publish_type_list")
        self.verticalLayout_2.addWidget(self.publish_type_list)

        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setSpacing(2)
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.check_all = QToolButton(self.left_area_widget)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.check_all.sizePolicy().hasHeightForWidth())
        self.check_all.setSizePolicy(sizePolicy)
        self.check_all.setMinimumSize(QSize(60, 26))
        self.check_all.setObjectName("check_all")
        self.horizontalLayout_6.addWidget(self.check_all)
        self.check_none = QToolButton(self.left_area_widget)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.check_none.sizePolicy().hasHeightForWidth())
        self.check_none.setSizePolicy(sizePolicy)
        self.check_none.setMinimumSize(QSize(75, 26))
        self.check_none.setObjectName("check_none")
        self.horizontalLayout_6.addWidget(self.check_none)
        self.label_3 = QLabel(self.left_area_widget)
        self.label_3.setText("")
        self.label_3.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout_6.addWidget(self.label_3)
        self.cog_button = QToolButton(self.left_area_widget)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/res/gear.png"), QIcon.Normal, QIcon.Off)
        self.cog_button.setIcon(icon)
        self.cog_button.setIconSize(QSize(20, 16))
        self.cog_button.setPopupMode(QToolButton.InstantPopup)
        self.cog_button.setObjectName("cog_button")
        self.horizontalLayout_6.addWidget(self.cog_button)
        self.verticalLayout_2.addLayout(self.horizontalLayout_6)
        self.middle_area_widget = QWidget(self.splitter)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.middle_area_widget.sizePolicy().hasHeightForWidth())
        self.middle_area_widget.setSizePolicy(sizePolicy)
        self.middle_area_widget.setObjectName("middle_area_widget")
        self.verticalLayout = QVBoxLayout(self.middle_area_widget)
        self.verticalLayout.setSpacing(2)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setSpacing(1)
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")

        # --- New Buttons ---
        self.refresh_button = QToolButton(self.middle_area_widget)
        self.refresh_button.setMinimumSize(QSize(40, 40))
        self.refresh_button.setMaximumSize(QSize(40, 40))
        icon_refresh = QIcon()
        icon_refresh.addPixmap(QPixmap(":/res/refresh.png"), QIcon.Normal, QIcon.Off) # Placeholder icon
        self.refresh_button.setIcon(icon_refresh)
        self.refresh_button.setObjectName("refresh_button")
        self.horizontalLayout_2.addWidget(self.refresh_button)

        self.get_latest_button = QToolButton(self.middle_area_widget)
        self.get_latest_button.setMinimumSize(QSize(40, 40))
        self.get_latest_button.setMaximumSize(QSize(40, 40))
        icon_get_latest = QIcon()
        icon_get_latest.addPixmap(QPixmap(":/res/get_latest.png"), QIcon.Normal, QIcon.Off) # Placeholder icon
        self.get_latest_button.setIcon(icon_get_latest)
        self.get_latest_button.setObjectName("get_latest_button")
        self.horizontalLayout_2.addWidget(self.get_latest_button)

        self.submit_button = QToolButton(self.middle_area_widget)
        self.submit_button.setMinimumSize(QSize(40, 40))
        self.submit_button.setMaximumSize(QSize(40, 40))
        icon_submit = QIcon()
        icon_submit.addPixmap(QPixmap(":/res/submit.png"), QIcon.Normal, QIcon.Off) # Placeholder icon
        self.submit_button.setIcon(icon_submit)
        self.submit_button.setObjectName("submit_button")
        self.horizontalLayout_2.addWidget(self.submit_button)
        # --- End New Buttons ---

        # Spacer to push breadcrumbs to the center
        spacerItem_before_bc = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem_before_bc)

        self.entity_breadcrumbs = QLabel(self.middle_area_widget)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred) # Changed from Ignored
        sizePolicy.setHorizontalStretch(1) # Allow stretch
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.entity_breadcrumbs.sizePolicy().hasHeightForWidth())
        self.entity_breadcrumbs.setSizePolicy(sizePolicy)
        self.entity_breadcrumbs.setMinimumSize(QSize(0, 40))
        self.entity_breadcrumbs.setText("")
        self.entity_breadcrumbs.setAlignment(Qt.AlignCenter) # Center align text
        self.entity_breadcrumbs.setObjectName("entity_breadcrumbs")
        self.horizontalLayout_2.addWidget(self.entity_breadcrumbs)

        # Spacer after breadcrumbs to help centering
        spacerItem = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum) # Changed from Ignored
        self.horizontalLayout_2.addItem(spacerItem)

        self.thumbnail_mode = QToolButton(self.middle_area_widget)
        self.thumbnail_mode.setMinimumSize(QSize(0, 26))
        icon1 = QIcon()
        icon1.addPixmap(QPixmap(":/res/mode_switch_thumb_active.png"), QIcon.Normal, QIcon.Off)
        self.thumbnail_mode.setIcon(icon1)
        self.thumbnail_mode.setCheckable(True)
        self.thumbnail_mode.setChecked(True)
        self.thumbnail_mode.setObjectName("thumbnail_mode")
        self.horizontalLayout_2.addWidget(self.thumbnail_mode)
        self.list_mode = QToolButton(self.middle_area_widget)
        self.list_mode.setMinimumSize(QSize(26, 26))
        icon2 = QIcon()
        icon2.addPixmap(QPixmap(":/res/mode_switch_card.png"), QIcon.Normal, QIcon.Off)
        self.list_mode.setIcon(icon2)
        self.list_mode.setCheckable(True)
        self.list_mode.setObjectName("list_mode")
        self.horizontalLayout_2.addWidget(self.list_mode)

        self.column_mode = QToolButton(self.middle_area_widget)
        self.column_mode.setMinimumSize(QSize(26, 26))
        icon3 = QIcon()
        icon3.addPixmap(QPixmap(":/res/mode_switch_column.png"), QIcon.Normal, QIcon.Off)
        self.column_mode.setIcon(icon3)
        self.column_mode.setCheckable(True)
        self.column_mode.setObjectName("column_mode")
        self.horizontalLayout_2.addWidget(self.column_mode)
        #self.column_mode.hide()

        self.submitted_mode = QToolButton(self.middle_area_widget)
        self.submitted_mode.setMinimumSize(QSize(26, 26))
        icon5 = QIcon()
        icon5.addPixmap(QPixmap(":/res/mode_switch_card.png"), QIcon.Normal, QIcon.Off)
        self.submitted_mode.setIcon(icon5)
        self.submitted_mode.setCheckable(True)
        self.submitted_mode.setObjectName("submitted_mode")
        self.horizontalLayout_2.addWidget(self.submitted_mode)

        self.pending_mode = QToolButton(self.middle_area_widget)
        self.pending_mode.setMinimumSize(QSize(26, 26))
        icon4 = QIcon()
        icon4.addPixmap(QPixmap(":/res/mode_switch_card.png"), QIcon.Normal, QIcon.Off)
        self.pending_mode.setIcon(icon4)
        self.pending_mode.setCheckable(True)
        self.pending_mode.setObjectName("pending_mode")
        self.horizontalLayout_2.addWidget(self.pending_mode)


        self.label_5 = QLabel(self.middle_area_widget)
        self.label_5.setMinimumSize(QSize(5, 0))
        self.label_5.setMaximumSize(QSize(5, 16777215))
        self.label_5.setText("")
        self.label_5.setObjectName("label_5")
        self.horizontalLayout_2.addWidget(self.label_5)
        self.search_publishes = QToolButton(self.middle_area_widget)
        self.search_publishes.setMinimumSize(QSize(0, 26))
        icon_search = QIcon() # Renamed icon variable
        icon_search.addPixmap(QPixmap(":/res/search.png"), QIcon.Normal, QIcon.Off)
        self.search_publishes.setIcon(icon_search)
        self.search_publishes.setCheckable(True)
        self.search_publishes.setObjectName("search_publishes")
        self.horizontalLayout_2.addWidget(self.search_publishes)
        self.info = QToolButton(self.middle_area_widget)
        self.info.setMinimumSize(QSize(80, 26))
        self.info.setObjectName("info")
        self.horizontalLayout_2.addWidget(self.info)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.publish_frame = QFrame(self.middle_area_widget)
        self.publish_frame.setObjectName("publish_frame")
        self.horizontalLayout_7 = QHBoxLayout(self.publish_frame)
        self.horizontalLayout_7.setSpacing(1)
        self.horizontalLayout_7.setContentsMargins(1, 1, 1, 1)
        self.horizontalLayout_7.setObjectName("horizontalLayout_7")

        self.publish_view = QListView(self.publish_frame)
        self.publish_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.publish_view.setResizeMode(QListView.Adjust)
        self.publish_view.setSpacing(5)
        self.publish_view.setViewMode(QListView.IconMode)
        self.publish_view.setUniformItemSizes(True)
        self.publish_view.setObjectName("publish_view")
        self.horizontalLayout_7.addWidget(self.publish_view)

        #self.column_view = QTableView(self.publish_frame)
        self.column_view = QTreeView(self.publish_frame)
        # Set the selection behavior to select whole rows
        self.column_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Set the header to be clickable for sorting        self.ui.column_view.header().setSectionsClickable(True)
        self.column_view.header().setSortIndicatorShown(True)
        # Sort by the first column initially
        self.column_view.sortByColumn(0, Qt.AscendingOrder)
        self.column_view.setSortingEnabled(True)
        self.column_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # Set the selection mode to single selection or multi-selection
        #self.column_view.setSelectionMode(QAbstractItemView.MultiSelection)

        self.horizontalLayout_7.addWidget(self.column_view)
        self.column_view.setVisible(False)

        self.perforce_scroll = QScrollArea(self.publish_frame)
        self.perforce_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.perforce_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # self.verticalLayout.addWidget(self.perforce_scroll)
        self.horizontalLayout_7.addWidget(self.perforce_scroll)
        self.perforce_scroll.setVisible(False)

        self.submitted_scroll = QScrollArea(self.publish_frame)
        self.submitted_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.submitted_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # self.verticalLayout.addWidget(self.submitted_scroll)
        self.horizontalLayout_7.addWidget(self.submitted_scroll)
        self.submitted_scroll.setVisible(False)

        self.pending_scroll = QScrollArea(self.publish_frame)
        self.pending_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.pending_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        #self.pending_scroll.setWidgetResizable(False)
        self.horizontalLayout_7.addWidget(self.pending_scroll)
        #self.verticalLayout.addWidget(self.pending_scroll)
        self.pending_scroll.setVisible(False)

        self.verticalLayout.addWidget(self.publish_frame)

        """
        self.publish_tabs = QTabWidget(Dialog)
        self.publish_tabs.setMaximumSize(QSize(650, 16777202))
        self.publish_tabs.setUsesScrollButtons(True)
        self.publish_tabs.setObjectName("publish_tabs")
        self.middle_area.addWidget(self.publish_tabs)
        """
        self.label_8 = QLabel(self.middle_area_widget)
        self.label_8.setAlignment(Qt.AlignCenter)
        self.label_8.setObjectName("label_8")
        self.label_8.setMinimumHeight(5)
        self.label_8.setMaximumHeight(5)
        self.verticalLayout.addWidget(self.label_8)

        self.log_window_container = QHBoxLayout()
        self.log_window_container.setObjectName("log_window_container")
        self.log_window = QTextBrowser()
        self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())
        self.log_window.setMinimumHeight(187)
        self.log_window.setMaximumHeight(187)
        self.log_window.setMinimumWidth(630)
        # self.log_window.setMaximumWidth(630)

        # self.log_window.setMinimumSize(QSize(100, 100))
        self.log_window_container.addWidget(self.log_window)
        self.verticalLayout.addLayout(self.log_window_container)

        self.horizontalLayout_4 = QHBoxLayout()
        # self.horizontalLayout_4.setContentsMargins(0, 4, 4, 4)
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.show_sub_items = QCheckBox(self.middle_area_widget)
        self.show_sub_items.setObjectName("show_sub_items")
        self.horizontalLayout_4.addWidget(self.show_sub_items)
        # self.show_sub_items.hide()

        self.fix_selected = QToolButton(self.middle_area_widget)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.fix_selected.sizePolicy().hasHeightForWidth())
        self.fix_selected.setSizePolicy(sizePolicy)
        self.fix_selected.setMinimumSize(QSize(100, 26))
        self.fix_selected.setMaximumSize(QSize(100, 26))
        self.fix_selected.setObjectName("fix_seleted")

        self.fix_all = QToolButton(self.middle_area_widget)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.fix_all.sizePolicy().hasHeightForWidth())
        self.fix_all.setSizePolicy(sizePolicy)
        self.fix_all.setMinimumSize(QSize(100, 26))
        self.fix_all.setMaximumSize(QSize(100, 26))
        self.fix_all.setObjectName("fix_all")

        self.sync_files = QToolButton(self.middle_area_widget)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sync_files.sizePolicy().hasHeightForWidth())
        self.sync_files.setSizePolicy(sizePolicy)
        self.sync_files.setMinimumSize(QSize(100, 26))
        self.sync_files.setMaximumSize(QSize(100, 26))
        self.sync_files.setObjectName("sync_files")

        self.sync_parents = QToolButton(self.middle_area_widget)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sync_parents.sizePolicy().hasHeightForWidth())
        self.sync_parents.setSizePolicy(sizePolicy)
        self.sync_parents.setMinimumSize(QSize(100, 26))
        self.sync_parents.setMaximumSize(QSize(100, 26))
        self.sync_parents.setObjectName("sync_files")

        self.submit_files = QToolButton(self.middle_area_widget)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.submit_files.sizePolicy().hasHeightForWidth())
        self.submit_files.setSizePolicy(sizePolicy)
        self.submit_files.setMinimumSize(QSize(100, 26))
        self.submit_files.setMaximumSize(QSize(100, 26))
        self.submit_files.setObjectName("publish_files")
        # Todo do we need to hide this? And move submit to the menu area?
        # self.submit_files.hide()

        self.progress = QProgressBar(self.middle_area_widget)
        self.progress.setMaximumHeight(20)
        self.progress.setMinimumWidth(350)
        self.progress.setMaximumWidth(350)
        self.progress.setRange(0, 100)
        # self.progress.setFormat("")
        self.progress.setVisible(False)

        # sp_retain = self.progress.sizePolicy()
        # sp_retain.setRetainSizeWhenHidden(True)
        # self.progress.setSizePolicy(sp_retain)

        self.horizontalLayout_4.addWidget(self.sync_files)
        self.horizontalLayout_4.addWidget(self.sync_parents)
        self.horizontalLayout_4.addWidget(self.fix_selected)
        self.horizontalLayout_4.addWidget(self.fix_all)
        self.horizontalLayout_4.addWidget(self.submit_files)
        self.horizontalLayout_4.addWidget(self.progress)
        spacerItem1 = QSpacerItem(128, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout_4.addItem(spacerItem1)
        self.scale_label = QLabel(self.middle_area_widget)
        self.scale_label.setText("")
        self.scale_label.setPixmap(QPixmap(":/res/search.png"))
        self.scale_label.setObjectName("scale_label")
        self.horizontalLayout_4.addWidget(self.scale_label)
        self.thumb_scale = QSlider(self.middle_area_widget)
        self.thumb_scale.setMinimumSize(QSize(100, 0))
        self.thumb_scale.setMaximumSize(QSize(100, 16777215))
        self.thumb_scale.setStyleSheet("QSlider::groove:horizontal {\n"
"     /*border: 1px solid #999999; */\n"
"     height: 2px; /* the groove expands to the size of the slider by default. by giving it a height, it has a fixed size */\n"
"     background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3F3F3F, stop:1 #545454);\n"
"     margin: 2px 0;\n"
"     border-radius: 1px;\n"
" }\n"
"\n"
" QSlider::handle:horizontal {\n"
"     background: #545454;\n"
"     border: 1px solid #B6B6B6;\n"
"     width: 5px;\n"
"     margin: -2px 0; /* handle is placed by default on the contents rect of the groove. Expand outside the groove */\n"
"     border-radius: 3px;\n"
" }\n"
"")
        self.thumb_scale.setMinimum(70)
        self.thumb_scale.setMaximum(250)
        self.thumb_scale.setProperty("value", 70)
        self.thumb_scale.setSliderPosition(70)
        self.thumb_scale.setOrientation(Qt.Horizontal)
        self.thumb_scale.setInvertedAppearance(False)
        self.thumb_scale.setInvertedControls(False)
        self.thumb_scale.setObjectName("thumb_scale")
        self.horizontalLayout_4.addWidget(self.thumb_scale)
        self.verticalLayout.addLayout(self.horizontalLayout_4)


        # Right area
        self.details_tab = QTabWidget(self.splitter)
        self.details_tab.setObjectName("tab_widget")

        # File details
        self.file_details = QGroupBox(self.splitter)
        self.file_details.setMinimumSize(QSize(0, 0))
        self.file_details.setMaximumSize(QSize(16777215, 16777215))
        self.file_details.setTitle("")
        self.file_details.setObjectName("details")
        self.verticalLayout_3 = QVBoxLayout(self.file_details)
        self.verticalLayout_3.setSpacing(2)
        self.verticalLayout_3.setContentsMargins(4, 4, 4, 4)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem2 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem2)
        self.file_details_image = QLabel(self.file_details)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.file_details_image.sizePolicy().hasHeightForWidth())
        self.file_details_image.setSizePolicy(sizePolicy)
        self.file_details_image.setMinimumSize(QSize(256, 200))
        self.file_details_image.setMaximumSize(QSize(256, 200))
        self.file_details_image.setScaledContents(True)
        self.file_details_image.setAlignment(Qt.AlignCenter)
        self.file_details_image.setObjectName("details_image")
        self.horizontalLayout.addWidget(self.file_details_image)
        spacerItem3 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem3)
        self.verticalLayout_3.addLayout(self.horizontalLayout)
        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.file_details_header = QLabel(self.file_details)
        self.file_details_header.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignTop)
        self.file_details_header.setWordWrap(True)
        self.file_details_header.setObjectName("details_header")
        self.horizontalLayout_5.addWidget(self.file_details_header)
        spacerItem4 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout_5.addItem(spacerItem4)
        self.verticalLayout_4 = QVBoxLayout()
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.file_detail_playback_btn = QToolButton(self.file_details)
        self.file_detail_playback_btn.setMinimumSize(QSize(55, 55))
        self.file_detail_playback_btn.setMaximumSize(QSize(55, 55))
        self.file_detail_playback_btn.setText("")
        icon_playback = QIcon() # Renamed icon variable
        icon_playback.addPixmap(QPixmap(":/res/play_icon.png"), QIcon.Normal, QIcon.Off)
        self.file_detail_playback_btn.setIcon(icon_playback)
        self.file_detail_playback_btn.setIconSize(QSize(40, 40))
        self.file_detail_playback_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.file_detail_playback_btn.setObjectName("detail_playback_btn")
        self.verticalLayout_4.addWidget(self.file_detail_playback_btn)
        self.file_detail_actions_btn = QToolButton(self.file_details)
        self.file_detail_actions_btn.setMinimumSize(QSize(55, 0))
        self.file_detail_actions_btn.setMaximumSize(QSize(55, 16777215))
        self.file_detail_actions_btn.setPopupMode(QToolButton.InstantPopup)
        self.file_detail_actions_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.file_detail_actions_btn.setObjectName("file_detail_actions_btn")
        self.verticalLayout_4.addWidget(self.file_detail_actions_btn)
        self.horizontalLayout_5.addLayout(self.verticalLayout_4)
        self.verticalLayout_3.addLayout(self.horizontalLayout_5)

        # File history
        self.verticalLayout_6 = QVBoxLayout()
        self.verticalLayout_6.setSpacing(2)
        self.verticalLayout_6.setObjectName("verticalLayout_6")

        self.version_file_history_label = QLabel(self.file_details)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.version_file_history_label.sizePolicy().hasHeightForWidth())
        self.version_file_history_label.setSizePolicy(sizePolicy)
        self.version_file_history_label.setStyleSheet("QLabel { padding-top: 14px}")
        self.version_file_history_label.setAlignment(Qt.AlignCenter)
        self.version_file_history_label.setWordWrap(True)
        self.version_file_history_label.setObjectName("version_file_history_label")
        self.verticalLayout_3.addWidget(self.version_file_history_label)
        self.file_history_view = QListView(self.file_details)
        self.file_history_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.file_history_view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.file_history_view.setUniformItemSizes(True)
        self.file_history_view.setObjectName("file_history_view")
        #self.verticalLayout_3.addWidget(self.file_history_view)


        self.verticalLayout_6.addWidget(self.file_history_view)
        self.verticalLayout_3.addLayout(self.verticalLayout_6)
        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setSpacing(2)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        spacerItem5 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout_3.addItem(spacerItem5)
        self.verticalLayout_3.addLayout(self.horizontalLayout_3)
        self.verticalLayout_5.addWidget(self.splitter)

        self.panel_details = QGroupBox(self.splitter)
        self.panel_details.setMinimumSize(QSize(0, 0))
        self.panel_details.setMaximumSize(QSize(16777215, 16777215))
        self.panel_details.setTitle("")
        self.panel_details.setObjectName("details")
        self.panel_layout = QVBoxLayout(self.panel_details)
        self.panel_layout.setSpacing(2)
        self.panel_layout.setContentsMargins(4, 4, 4, 4)
        self.panel_layout.setObjectName("panel_layout")


        self.details_tab.addTab(self.file_details, "Files")
        self.details_tab.addTab(self.panel_details, "Panel")


        self.retranslateUi(Dialog)
        self.entity_preset_tabs.setCurrentIndex(-1)
        QMetaObject.connectSlotsByName(Dialog)
        Dialog.setTabOrder(self.navigation_home, self.navigation_prev)
        Dialog.setTabOrder(self.navigation_prev, self.navigation_next)
        # --- Update Tab Order ---
        Dialog.setTabOrder(self.navigation_next, self.refresh_button)
        Dialog.setTabOrder(self.refresh_button, self.get_latest_button)
        Dialog.setTabOrder(self.get_latest_button, self.submit_button)
        Dialog.setTabOrder(self.submit_button, self.publish_type_list)
        # --- End Update Tab Order ---
        Dialog.setTabOrder(self.publish_type_list, self.show_sub_items)
        Dialog.setTabOrder(self.show_sub_items, self.sync_files)
        Dialog.setTabOrder(self.sync_files, self.sync_parents)
        Dialog.setTabOrder(self.sync_parents, self.fix_selected)
        Dialog.setTabOrder(self.fix_selected, self.fix_all)
        Dialog.setTabOrder(self.fix_all, self.submit_files)
        Dialog.setTabOrder(self.submit_files, self.thumb_scale)
        Dialog.setTabOrder(self.thumb_scale, self.file_history_view)

        self.sync_files.setEnabled(True)
        self.sync_parents.setEnabled(True)
        self.fix_selected.setEnabled(False)
        self.fix_all.setEnabled(False)
        self.submit_files.setEnabled(False)

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QApplication.translate("Dialog", "Load items into your scene", None, QApplication.UnicodeUTF8))
        self.navigation_home.setToolTip(QApplication.translate("Dialog", "Clicking the <i>home button</i> will take you to the location that best matches your current work area.", None, QApplication.UnicodeUTF8))
        self.navigation_home.setAccessibleName(QApplication.translate("Dialog", "navigation_home", None, QApplication.UnicodeUTF8))
        self.navigation_prev.setToolTip(QApplication.translate("Dialog", "<i>Go back</i> in the folder file_history.", None, QApplication.UnicodeUTF8))
        self.navigation_prev.setAccessibleName(QApplication.translate("Dialog", "navigation_prev", None, QApplication.UnicodeUTF8))
        self.navigation_next.setToolTip(QApplication.translate("Dialog", "<i>Go forward</i> in the folder file_history.", None, QApplication.UnicodeUTF8))
        self.navigation_next.setAccessibleName(QApplication.translate("Dialog", "navigation_next", None, QApplication.UnicodeUTF8))
        # --- New Tooltips ---
        self.refresh_button.setToolTip(QApplication.translate("Dialog", "Refresh the current view.", None, QApplication.UnicodeUTF8))
        self.refresh_button.setAccessibleName(QApplication.translate("Dialog", "refresh_button", None, QApplication.UnicodeUTF8))
        self.get_latest_button.setToolTip(QApplication.translate("Dialog", "Get the latest version of selected files.", None, QApplication.UnicodeUTF8))
        self.get_latest_button.setAccessibleName(QApplication.translate("Dialog", "get_latest_button", None, QApplication.UnicodeUTF8))
        self.submit_button.setToolTip(QApplication.translate("Dialog", "Submit selected files to Perforce.", None, QApplication.UnicodeUTF8))
        self.submit_button.setAccessibleName(QApplication.translate("Dialog", "submit_button", None, QApplication.UnicodeUTF8))
        # --- End New Tooltips ---
        self.entity_preset_tabs.setToolTip(QApplication.translate("Dialog", "This area shows <i>ShotGrid objects</i> such as Shots or Assets, grouped into sections. ", None, QApplication.UnicodeUTF8))
        self.entity_preset_tabs.setAccessibleName(QApplication.translate("Dialog", "entity_preset_tabs", None, QApplication.UnicodeUTF8))
        self.label_4.setText(QApplication.translate("Dialog", "<small>Filter by Published File Type</small>", None, QApplication.UnicodeUTF8))
        self.publish_type_list.setToolTip(QApplication.translate("Dialog", "This list shows all the relevant <i>publish types</i> for your current selection. By ticking and unticking items in this list, publishes in the main view will be shown or hidden. You can see a summary count next to each publish type, showing how many items of that sort are matching your current selection.", None, QApplication.UnicodeUTF8))
        self.publish_type_list.setAccessibleName(QApplication.translate("Dialog", "publish_type_list", None, QApplication.UnicodeUTF8))
        self.check_all.setText(QApplication.translate("Dialog", "Select All", None, QApplication.UnicodeUTF8))
        self.check_none.setText(QApplication.translate("Dialog", "Select None", None, QApplication.UnicodeUTF8))
        self.fix_selected.setToolTip(QApplication.translate("Dialog", "Publish selected files in the Submitted view", None, QApplication.UnicodeUTF8))
        self.fix_selected.setText(QApplication.translate("Dialog", "Fix Selected", None, QApplication.UnicodeUTF8))
        self.fix_all.setToolTip(QApplication.translate("Dialog", "Publish all files in the Submitted view", None, QApplication.UnicodeUTF8))
        self.fix_all.setText(QApplication.translate("Dialog", "Fix All", None, QApplication.UnicodeUTF8))

        # self.sync_files.setToolTip(QApplication.translate("Dialog", "Sync files in the <i>Sync Queue</i>. Please note that you must click on <i>Add to Queue</i> first before syncing.", None, QApplication.UnicodeUTF8))
        self.sync_files.setText(QApplication.translate("Dialog", "Sync Files", None, QApplication.UnicodeUTF8))
        self.sync_parents.setText(QApplication.translate("Dialog", "Sync Parents", None, QApplication.UnicodeUTF8))

        self.submit_files.setText(QApplication.translate("Dialog", "Submit Files", None, QApplication.UnicodeUTF8))
        self.submit_files.setToolTip(QApplication.translate("Dialog", "Submit checked files in the Pending view to the Shotgrid Publisher.", None, QApplication.UnicodeUTF8))

        self.cog_button.setToolTip(QApplication.translate("Dialog", "Tools and Settings", None, QApplication.UnicodeUTF8))
        self.cog_button.setAccessibleName(QApplication.translate("Dialog", "cog_button", None, QApplication.UnicodeUTF8))
        self.entity_breadcrumbs.setToolTip(QApplication.translate("Dialog", "This <i>breadcrumbs listing</i> shows your currently selected ShotGrid location.", None, QApplication.UnicodeUTF8))
        self.thumbnail_mode.setToolTip(QApplication.translate("Dialog", "Thumbnail Mode", None, QApplication.UnicodeUTF8))
        self.thumbnail_mode.setAccessibleName(QApplication.translate("Dialog", "thumbnail_mode", None, QApplication.UnicodeUTF8))
        self.thumbnail_mode.setText(QApplication.translate("Dialog", "...", None, QApplication.UnicodeUTF8))
        self.list_mode.setToolTip(QApplication.translate("Dialog", "List Mode", None, QApplication.UnicodeUTF8))
        self.list_mode.setAccessibleName(QApplication.translate("Dialog", "list_mode", None, QApplication.UnicodeUTF8))
        self.list_mode.setText(QApplication.translate("Dialog", "...", None, QApplication.UnicodeUTF8))
        self.column_mode.setToolTip(QApplication.translate("Dialog", "Column Mode", None, QApplication.UnicodeUTF8))
        self.column_mode.setAccessibleName(QApplication.translate("Dialog", "column_mode", None, QApplication.UnicodeUTF8))
        self.column_mode.setText(QApplication.translate("Dialog", "...", None, QApplication.UnicodeUTF8))
        self.pending_mode.setToolTip(QApplication.translate("Dialog", "Pending Mode", None, QApplication.UnicodeUTF8))
        self.pending_mode.setAccessibleName(QApplication.translate("Dialog", "pending_mode", None, QApplication.UnicodeUTF8))
        self.pending_mode.setText(QApplication.translate("Dialog", "...", None, QApplication.UnicodeUTF8))
        self.submitted_mode.setToolTip(QApplication.translate("Dialog", "Submitted Mode", None, QApplication.UnicodeUTF8))
        self.submitted_mode.setAccessibleName(QApplication.translate("Dialog", "submitted_mode", None, QApplication.UnicodeUTF8))
        self.submitted_mode.setText(QApplication.translate("Dialog", "...", None, QApplication.UnicodeUTF8))

        self.search_publishes.setToolTip(QApplication.translate("Dialog", "Filter Publishes", None, QApplication.UnicodeUTF8))
        self.search_publishes.setAccessibleName(QApplication.translate("Dialog", "search_publishes", None, QApplication.UnicodeUTF8))
        self.info.setToolTip(QApplication.translate("Dialog", "Use this button to <i>toggle details on and off</i>. ", None, QApplication.UnicodeUTF8))
        self.info.setText(QApplication.translate("Dialog", "Show Details", None, QApplication.UnicodeUTF8))
        self.publish_view.setAccessibleName(QApplication.translate("Dialog", "publish_view", None, QApplication.UnicodeUTF8))
        self.show_sub_items.setToolTip(QApplication.translate("Dialog", "Enables the <i>subfolder mode</i>, displaying a total aggregate of all selected items.", None, QApplication.UnicodeUTF8))
        self.show_sub_items.setAccessibleName(QApplication.translate("Dialog", "show_sub_items", None, QApplication.UnicodeUTF8))
        self.show_sub_items.setText(QApplication.translate("Dialog", "Show items in subfolders", None, QApplication.UnicodeUTF8))
        # self.label_8.setText(QApplication.translate("Dialog", "<small>Progress</small>", None, QApplication.UnicodeUTF8))
        self.thumb_scale.setToolTip(QApplication.translate("Dialog", "Use this handle to <i>adjust the size</i> of the displayed thumbnails.", None, QApplication.UnicodeUTF8))
        self.thumb_scale.setAccessibleName(QApplication.translate("Dialog", "thumb_scale", None, QApplication.UnicodeUTF8))

        self.file_details_image.setAccessibleName(QApplication.translate("Dialog", "file_details_image", None, QApplication.UnicodeUTF8))
        self.file_details_image.setText(QApplication.translate("Dialog", "TextLabel", None, QApplication.UnicodeUTF8))
        #self.file_details_header.setText(QApplication.translate("Dialog", "TextLabel", None, QApplication.UnicodeUTF8))
        self.file_detail_playback_btn.setToolTip(QApplication.translate("Dialog", "The most recent published version has some playable media associated. Click this button to launch the ShotGrid <b>Media Center</b> web player to see the review version and any notes and comments that have been submitted.", None, QApplication.UnicodeUTF8))
        self.file_detail_actions_btn.setText(QApplication.translate("Dialog", "Actions", None, QApplication.UnicodeUTF8))
        self.version_file_history_label.setText(QApplication.translate("Dialog", "<small>Complete Version File History</small>", None, QApplication.UnicodeUTF8))
        self.file_history_view.setAccessibleName(QApplication.translate("Dialog", "file_history_view", None, QApplication.UnicodeUTF8))
        """
        self.entity_details_image.setAccessibleName(QApplication.translate("Dialog", "entity_details_image", None, QApplication.UnicodeUTF8))
        self.entity_details_image.setText(QApplication.translate("Dialog", "Entity Image", None, QApplication.UnicodeUTF8))
        #self.entity_details_header.setText(QApplication.translate("Dialog", "TextLabel", None, QApplication.UnicodeUTF8))
        # self.entity_detail_playback_btn.setToolTip(QApplication.translate("Dialog", "The most recent published version has some playable media associated. Click this button to launch the ShotGrid <b>Media Center</b> web player to see the review version and any notes and comments that have been submitted.", None, QApplication.UnicodeUTF8))
        #self.entity_detail_actions_btn.setText(QApplication.translate("Dialog", "Actions", None, QApplication.UnicodeUTF8))
        self.entity_parents_label.setText(QApplication.translate("Dialog", "<small>Complete Entity Parents and Children</small>", None, QApplication.UnicodeUTF8))
        self.entity_parents_view.setAccessibleName(QApplication.translate("Dialog", "parents_history_view", None, QApplication.UnicodeUTF8))
        #self.entity_children_label.setText(QApplication.translate("Dialog", "<small>Complete Children History</small>", None, QApplication.UnicodeUTF8))
        self.entity_children_view.setAccessibleName(QApplication.translate("Dialog", "parents_history_view", None, QApplication.UnicodeUTF8))
        #self.sync_entity_files.setToolTip(QApplication.translate("Dialog", "Sync All", None, QApplication.UnicodeUTF8))
        #self.sync_entity_files.setText(QApplication.translate("Dialog", "Sync Alll", None, QApplication.UnicodeUTF8))
        """
from . import resources_rc
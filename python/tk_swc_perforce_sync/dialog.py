# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


import sgtk
from sgtk.util import login
from sgtk import TankError

from sgtk.platform.qt import QtCore
for name, cls in QtCore.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

from sgtk.platform.qt import QtGui
for name, cls in QtGui.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

import threading
from .threads import SyncThread, FileSyncThread
import concurrent.futures
import subprocess
import queue
import re
import concurrent.futures


import datetime

from .date_time import create_publish_timestamp, create_human_readable_timestamp, create_modified_date, create_human_readable_date, get_time_now

from .model_hierarchy import SgHierarchyModel
from .model_entity import SgEntityModel
from .model_latestpublish import SgLatestPublishModel
from .model_entitypublish import SgEntityPublishModel
from .model_publishtype import SgPublishTypeModel
from .model_status import SgStatusModel
from .proxymodel_latestpublish import SgLatestPublishProxyModel
from .proxymodel_entity import SgEntityProxyModel
from .delegate_publish_thumb import SgPublishThumbDelegate
from .delegate_publish_list import SgPublishListDelegate
from .model_publishhistory import SgPublishHistoryModel
from .delegate_publish_history import SgPublishHistoryDelegate

from .search_widget import SearchWidget
from .banner import Banner
from .loader_action_manager import LoaderActionManager
from .utils import resolve_filters, get_action_icon
from .utils import Icons

from .utils import check_validity_by_path_parts, check_validity_by_published_file


from . import constants
from . import model_item_data

from .ui.dialog import Ui_Dialog
from .publish_item import PublishItem

from .publish_files_ui import PublishFilesUI

from .perforce_change import create_change, add_to_change, submit_change, submit_and_delete_file, submit_single_file, submit_and_delete_file_list
from .treeview_widget import TreeViewWidget, SWCTreeView
from .submit_changelist_widget import SubmitChangelistWidget
from .changelist_selection_operation import ChangelistSelection
from collections import defaultdict, OrderedDict
import os
from os.path import expanduser
import sys
import time
import tempfile

logger = sgtk.platform.get_logger(__name__)
import logging

# import frameworks
shotgun_model = sgtk.platform.import_framework(
    "tk-swc-framework-shotgunutils", "shotgun_model"
)
settings = sgtk.platform.import_framework("tk-swc-framework-shotgunutils", "settings")
help_screen = sgtk.platform.import_framework("tk-framework-qtwidgets", "help_screen")
overlay_widget = sgtk.platform.import_framework(
    "tk-framework-qtwidgets", "overlay_widget"
)
shotgun_search_widget = sgtk.platform.import_framework(
    "tk-framework-qtwidgets", "shotgun_search_widget"
)
task_manager = sgtk.platform.import_framework(
    "tk-swc-framework-shotgunutils", "task_manager"
)
shotgun_globals = sgtk.platform.import_framework(
    "tk-swc-framework-shotgunutils", "shotgun_globals"
)

swc_fw = sgtk.platform.import_framework(
    "tk-framework-swc", "Context_Utils"
)

ShotgunModelOverlayWidget = overlay_widget.ShotgunModelOverlayWidget


class AppDialog(QWidget):
    """
    Main dialog window for the App
    """

    # enum to control the mode of the main view
    (MAIN_VIEW_LIST, MAIN_VIEW_THUMB, MAIN_VIEW_COLUMN, MAIN_VIEW_SUBMITTED, MAIN_VIEW_PENDING) = range(5)
    # enum to control the grouping of the column view
    (COLUMN_VIEW_UNGROUP, COLUMN_VIEW_GROUP_BY_FOLDER, COLUMN_VIEW_GROUP_BY_ACTION, COLUMN_VIEW_GROUP_BY_REVISION,
     COLUMN_VIEW_GROUP_BY_EXTENSION, COLUMN_VIEW_GROUP_BY_TYPE, COLUMN_VIEW_GROUP_BY_USER, COLUMN_VIEW_GROUP_BY_TASK,
     COLUMN_VIEW_GROUP_BY_STATUS, COLUMN_VIEW_GROUP_BY_STEP, COLUMN_VIEW_GROUP_BY_DATE_MODIFIED) = range(11)

    # signal emitted whenever the selected publish changes
    # in either the main view or the details file_history view
    selection_changed = QtCore.Signal()
    update_pending_view_signal = QtCore.Signal()
    # update_pending_view_signal = pyqtQtCore.Signal()

    def __init__(self, action_manager, parent=None):
        super(AppDialog, self).__init__()  # Ensure proper parent initialization
        """
        Constructor

        :param action_manager:  The action manager to use - if not specified
                                then the default will be used instead
        :param parent:          The parent QWidget for this control
        """
       #QWidget.__init__(self, parent)
        self._action_manager = action_manager

        # The loader app can be invoked from other applications with a custom
        # action manager as a File Open-like dialog. For these managers, we won't
        # be using the banner system.

        # We will support the banners only for the default loader.
        if isinstance(action_manager, LoaderActionManager):
            self._action_banner = Banner(self)
            self._action_manager.pre_execute_action.connect(self._pre_execute_action)
            self._action_manager.post_execute_action.connect(
                lambda _: self._action_banner.hide_banner()
            )

        # create a settings manager where we can pull and push prefs later
        # prefs in this manager are shared
        self._settings_manager = settings.UserSettings(sgtk.platform.current_bundle())

        # create a background task manager
        self._task_manager = task_manager.BackgroundTaskManager(
            self, start_processing=True, max_threads=2
        )

        shotgun_globals.register_bg_task_manager(self._task_manager)

        # set up the UI
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self._app = sgtk.platform.current_bundle()
        #################################################
        # Perforce Views
        self.main_view_mode = self.MAIN_VIEW_THUMB
        self.repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

        active_refresh_button_image_path = os.path.join(self.repo_root, "icons/refresh_active_20.png")
        self.active_refresh_button_icon = QIcon(QPixmap(active_refresh_button_image_path))

        active_get_latest_image_path = os.path.join(self.repo_root, "icons/get_latest_active_20")
        self.active_get_latest_button_icon = QIcon(QPixmap(active_get_latest_image_path))

        active_submit_button_image_path = os.path.join(self.repo_root, "icons/submit_active_20")
        self.active_submit_button_icon = QIcon(QPixmap(active_submit_button_image_path))

        inactive_refresh_button_image_path = os.path.join(self.repo_root, "icons/refresh_off_20.png")
        self.inactive_refresh_button_icon = QIcon(QPixmap(inactive_refresh_button_image_path))

        inactive_get_latest_image_path = os.path.join(self.repo_root, "icons/get_latest_off_20")
        self.inactive_get_latest_button_icon = QIcon(QPixmap(inactive_get_latest_image_path))

        inactive_submit_button_image_path = os.path.join(self.repo_root, "icons/submit_off_20")
        self.inactive_submit_button_icon = QIcon(QPixmap(inactive_submit_button_image_path))

        active_column_view_image_path = os.path.join(self.repo_root, "icons/mode_switch_column_active.png")
        self.active_column_view_icon = QIcon(QPixmap(active_column_view_image_path))

        inactive_column_view_image_path = os.path.join(self.repo_root, "icons/mode_switch_column_off.png")
        self.inactive_column_view_icon = QIcon(QPixmap(inactive_column_view_image_path))

        submitted_image_path = os.path.join(self.repo_root, "icons/mode_switch_submitted_active.png")
        self.submitted_icon = QIcon(QPixmap(submitted_image_path))

        inactive_submitted_image_path = os.path.join(self.repo_root, "submitted_off.png")
        self.submitted_icon_inactive = QIcon(QPixmap(inactive_submitted_image_path))

        pending_image_path = os.path.join(self.repo_root, "icons/mode_switch_pending_active.png")
        self.pending_icon = QIcon(QPixmap(pending_image_path))

        inactive_pending_image_path = os.path.join(self.repo_root, "icons/pending_off.png")
        # self.inactive_pending_icon = QIcon(QPixmap(inactive_pending_image_path))
        self.pending_icon_inactive = QIcon(QPixmap(inactive_pending_image_path))

        #################################################
        # Perforce
        self._fw = sgtk.platform.get_framework("tk-framework-perforce")
        self._p4 = self._fw.connection.connect()
        # Entity
        self._entity_path = None
        self._entity_data = None
        #self._set_perforce_buttons()
        #################################################
        # maintain a list where we keep a reference to
        # all the dynamic UI we create. This is to make
        # the GC happy.
        self._dynamic_widgets = []

        # maintain a special flag so that we can switch profile
        # tabs without triggering events
        self._disable_tab_event_handler = False
        #################################################
        # Icons:
        self.actions_icons = Icons()
        self.sync_icons = Icons()
        #################################################
        # hook a helper model tracking status codes so we
        # can use those in the UI
        self._status_model = SgStatusModel(self, self._task_manager)

        #################################################
        # details pane
        self._details_pane_visible = False

        self._file_details_action_menu = QMenu()
        self.ui.file_detail_actions_btn.setMenu(self._file_details_action_menu)

        self.ui.info.clicked.connect(self._toggle_details_pane)

        self.ui.refresh_button.clicked.connect(self._refresh_all)
        self.ui.get_latest_button.clicked.connect(self._get_latest)
        self.ui.submit_button.clicked.connect(self._submit_pending)

        self.ui.thumbnail_mode.clicked.connect(self._on_thumbnail_mode_clicked)
        self.ui.list_mode.clicked.connect(self._on_list_mode_clicked)
        self.ui.column_mode.clicked.connect(self._on_column_mode_clicked)
        self.ui.submitted_mode.clicked.connect(self._on_submitted_mode_clicked)
        self.ui.pending_mode.clicked.connect(self._on_pending_mode_clicked)

        self.update_pending_view_signal.connect(self.update_pending_view)
        ###########################################
        # Shotgun Panel
        #
        # Connect the tab change signal to the slot
        self.shotgun_panel_widget = None
        self._get_shotgun_panel_widget()
        #self.ui.details_tab.currentChanged.connect(self._on_details_tab_changed)


        ###########################################
        # File History
        self._publish_file_history_model = SgPublishHistoryModel(self, self._task_manager)

        self._publish_file_history_model_overlay = ShotgunModelOverlayWidget(
            self._publish_file_history_model, self.ui.file_history_view
        )

        self._publish_file_history_proxy = QtGui.QSortFilterProxyModel(self)
        self._publish_file_history_proxy.setSourceModel(self._publish_file_history_model)

        # now use the proxy model to sort the data to ensure
        # higher version numbers appear earlier in the list
        # the file_history model is set up so that the default display
        # role contains the version number field in shotgun.
        # This field is what the proxy model sorts by default
        # We set the dynamic filter to true, meaning QT will keep
        # continously sorting. And then tell it to use column 0
        # (we only have one column in our models) and descending order.
        self._publish_file_history_proxy.setDynamicSortFilter(True)
        self._publish_file_history_proxy.sort(0, Qt.DescendingOrder)

        self.ui.file_history_view.setModel(self._publish_file_history_proxy)
        self._file_history_delegate = SgPublishHistoryDelegate(
            self.ui.file_history_view, self._status_model, self._action_manager
        )
        self.ui.file_history_view.setItemDelegate(self._file_history_delegate)

        # event handler for when the selection in the file_history view is changing
        # note! Because of some GC issues (maya 2012 Pyside), need to first establish
        # a direct reference to the selection model before we can set up any signal/slots
        # against it
        self._file_history_view_selection_model = self.ui.file_history_view.selectionModel()
        self._file_history_view_selection_model.selectionChanged.connect(
            self._on_file_history_selection
        )

        self._multiple_publishes_pixmap = QPixmap(
            ":/res/multiple_publishes_512x400.png"
        )
        self._no_selection_pixmap = QPixmap(":/res/no_item_selected_512x400.png")
        self._no_pubs_found_icon = QPixmap(":/res/no_publishes_found.png")

        self.ui.file_detail_playback_btn.clicked.connect(self._on_detail_version_playback)
        self._current_version_detail_playback_url = None

        # set up right click menu for the main publish view
        self._refresh_file_history_action = QAction("Refresh", self.ui.file_history_view)
        self._refresh_file_history_action.triggered.connect(
            self._publish_file_history_model.async_refresh
        )
        self.ui.file_history_view.addAction(self._refresh_file_history_action)
        self.ui.file_history_view.setContextMenuPolicy(Qt.ActionsContextMenu)

        # if an item in the list is double clicked the default action is run
        self.ui.file_history_view.doubleClicked.connect(self._on_file_history_double_clicked)
        ###########################################
        # Entity Parents publish model
        self._temp_dir = tempfile.mkdtemp()

        # load and initialize cached publish type model
        self._entity_parents_type_model = SgPublishTypeModel(
            self, self._action_manager, self._settings_manager, self._task_manager
        )
        self.ui.publish_type_list.setModel(self._entity_parents_type_model)

        self._entity_parents_type_overlay = ShotgunModelOverlayWidget(
            self._entity_parents_type_model, self.ui.publish_type_list
        )

        self._entity_parents_model = SgEntityPublishModel(
            self, self._entity_parents_type_model, self._task_manager
        )

        # set up a proxy model to cull results based on type selection
        self._entity_parents_proxy_model = SgLatestPublishProxyModel(self)
        self._entity_parents_proxy_model.setSourceModel(self._entity_parents_model)

        # Entity Parents History
        self._publish_entity_parents_model = SgPublishHistoryModel(self, self._task_manager)


        self._publish_entity_parents_proxy = QtGui.QSortFilterProxyModel(self)
        self._publish_entity_parents_proxy.setSourceModel(self._publish_entity_parents_model)

        # now use the proxy model to sort the data to ensure
        # higher version numbers appear earlier in the list
        # the entity_parents model is set up so that the default display
        # role contains the version number field in shotgun.
        # This field is what the proxy model sorts by default
        # We set the dynamic filter to true, meaning QT will keep
        # continously sorting. And then tell it to use column 0
        # (we only have one column in our models) and descending order.
        self._publish_entity_parents_proxy.setDynamicSortFilter(True)
        self._publish_entity_parents_proxy.sort(0, Qt.DescendingOrder)

        #################################################
        # load and initialize cached publish type model
        self._publish_type_model = SgPublishTypeModel(
            self, self._action_manager, self._settings_manager, self._task_manager
        )
        self.ui.publish_type_list.setModel(self._publish_type_model)

        self._publish_type_overlay = ShotgunModelOverlayWidget(
            self._publish_type_model, self.ui.publish_type_list
        )

        #################################################
        # setup publish model
        self._publish_model = SgLatestPublishModel(
            self, self._publish_type_model, self._task_manager
        )

        self._publish_main_overlay = ShotgunModelOverlayWidget(
            self._publish_model, self.ui.publish_view
        )

        # set up a proxy model to cull results based on type selection
        self._publish_proxy_model = SgLatestPublishProxyModel(self)
        self._publish_proxy_model.setSourceModel(self._publish_model)

        # whenever the number of columns change in the proxy model
        # check if we should display the "sorry, no publishes found" overlay
        self._publish_model.cache_loaded.connect(self._on_publish_content_change)
        self._publish_model.data_refreshed.connect(self._on_publish_content_change)
        self._publish_proxy_model.filter_changed.connect(
            self._on_publish_content_change
        )

        # hook up view -> proxy model -> model
        self.ui.publish_view.setModel(self._publish_proxy_model)

        # set up custom delegates to use when drawing the main area
        self._publish_thumb_delegate = SgPublishThumbDelegate(
            self.ui.publish_view, self._action_manager
        )

        self._publish_list_delegate = SgPublishListDelegate(
            self.ui.publish_view, self._action_manager
        )

        # recall which the most recently mode used was and set that
        #main_view_mode = self._settings_manager.retrieve(
        #    "main_view_mode", self.MAIN_VIEW_THUMB
        #)
        # self._set_main_view_mode(main_view_mode)
        self._set_main_view_mode(self.MAIN_VIEW_THUMB)

        # whenever the type list is checked, update the publish filters
        self._publish_type_model.itemChanged.connect(
            self._apply_type_filters_on_publishes
        )

        # if an item in the table is double clicked the default action is run
        self.ui.publish_view.doubleClicked.connect(self._on_publish_double_clicked)

        # event handler for when the selection in the publish view is changing
        # note! Because of some GC issues (maya 2012 Pyside), need to first establish
        # a direct reference to the selection model before we can set up any signal/slots
        # against it
        self.ui.publish_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._publish_view_selection_model = self.ui.publish_view.selectionModel()
        self._publish_view_selection_model.selectionChanged.connect(
            self._on_publish_selection
        )

        # set up right click menu for the main publish view

        self._fix_action = QAction("Fix", self.ui.publish_view)
        self._fix_action.triggered.connect(lambda: self._on_publish_model_action("fix"))

        self._add_action = QAction("Add", self.ui.publish_view)
        self._add_action.triggered.connect(lambda: self._on_publish_model_action("add"))
        self._edit_action = QAction("Edit", self.ui.publish_view)
        self._edit_action.triggered.connect(lambda: self._on_publish_model_action("edit"))
        self._delete_action = QAction("Delete", self.ui.publish_view)
        self._delete_action.triggered.connect(lambda: self._on_publish_model_action("delete"))
        # Add changlist as submenus to the delete action

        self._change_lists = QAction("1001", self._delete_action)
        self._change_lists.triggered.connect(lambda: self._on_publish_model_action("1001"))

        self._revert_action = QAction("Revert", self.ui.publish_view)
        self._revert_action.triggered.connect(lambda: self._on_publish_model_action("revert"))

        # Correctly connect the triggered signal to the slot
        self._preview_create_folders_action = QAction("Preview Create Folders", self.ui.publish_view)
        self._preview_create_folders_action.triggered.connect(lambda: self._on_publish_folder_action("preview"))

        self._create_folders_action = QAction("Create Folders", self.ui.publish_view)
        self._create_folders_action.triggered.connect(lambda: self._on_publish_folder_action("create"))

        self._unregister_folders_action = QAction("Unregister Folders", self.ui.publish_view)
        self._unregister_folders_action.triggered.connect(lambda: self._on_publish_folder_action("unregister"))

        self._refresh_action = QAction("Refresh", self.ui.publish_view)
        self._refresh_action.triggered.connect(self._publish_model.async_refresh)

        self.ui.publish_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.publish_view.customContextMenuRequested.connect(
            self._show_publish_actions
        )

        #################################################
        # popdown publish filter widget for the main view
        # note:
        # we parent the widget to a frame that flows around the
        # main publish area - this is in order to avoid a scenario
        # where the overlay that sometimes pops up on top of the
        # publish area and the search widget would be competing
        # for the same z-index. The result in some of these cases
        # is that the search widget is hidden under the "publishes
        # not found" overlay. By having it parented to the frame
        # instead, it will always be above the overlay.
        self._search_widget = SearchWidget(self.ui.publish_frame)
        # hook it up with the search button the main toolbar
        self.ui.search_publishes.clicked.connect(self._on_publish_filter_clicked)
        # hook it up so that it signals the publish proxy model whenever the filter changes
        self._search_widget.filter_changed.connect(
            self._publish_proxy_model.set_search_query
        )
        self._search_widget.filter_changed.connect(
            self._on_column_view_set_search_query
        )
        self._column_view_search_filter = None

        #################################################
        # checkboxes, buttons etc
        self.ui.fix_selected.clicked.connect(self._on_fix_selected)
        self.ui.fix_all.clicked.connect(self._on_fix_all)
        self.ui.sync_files.clicked.connect(self._on_sync_files)
        self.ui.sync_parents.clicked.connect(self._on_sync_parents)
        self.ui.submit_files.clicked.connect(self._on_submit_files)
        # self.ui.show_sub_items.toggled.connect(self._on_show_subitems_toggled)

        self.ui.check_all.clicked.connect(self._publish_type_model.select_all)
        self.ui.check_none.clicked.connect(self._publish_type_model.select_none)
        # self.ui.sync_entity_files.clicked.connect(self._on_sync_entity_files)


        #################################################
        # thumb scaling
        scale_val = self._settings_manager.retrieve("thumb_size_scale", 140)
        # position both slider and view
        self.ui.thumb_scale.setValue(scale_val)
        self.ui.publish_view.setIconSize(QSize(scale_val, scale_val))
        # and track subsequent changes
        self.ui.thumb_scale.valueChanged.connect(self._on_thumb_size_slider_change)

        #################################################
        #Table view setup
        self._headers = ["", "Folder", "Action", "Name", "Revision#", "Size(MB)", "Extension", "Type",
                         "User", "Task", "Status", "Step", "Date/Time", "Date Modified", "ID",
                         "Description"]
        self._setup_column_view()
        self._current_column_view_grouping = self.COLUMN_VIEW_UNGROUP

        #################################################
        # setup file_history

        self._file_history = []
        self._file_history_index = 0
        # state flag used by file_history tracker to indicate that the
        # current navigation operation is happen as a part of a
        # back/forward operation and not part of a user's click
        self._file_history_navigation_mode = False
        self.ui.navigation_home.clicked.connect(self._on_home_clicked)
        self.ui.navigation_prev.clicked.connect(self._on_back_clicked)
        self.ui.navigation_next.clicked.connect(self._on_forward_clicked)
        #################################################
        # setup entity parents

        self._entity_parents = []
        self._entity_parents_index = 0
        # state flag used by entity_parents tracker to indicate that the
        # current navigation operation is happen as a part of a
        # back/forward operation and not part of a user's click
        self._entity_parents_navigation_mode = False

        #################################################
        # setup entity children

        self._entity_children = []
        self._entity_children_index = 0
        # state flag used by entity_children tracker to indicate that the
        # current navigation operation is happen as a part of a
        # back/forward operation and not part of a user's click
        self._entity_children_navigation_mode = False


        #################################################
        # set up cog button actions
        self._help_action = QAction("Show Help Screen", self)
        self._help_action.triggered.connect(self.show_help_popup)
        self.ui.cog_button.addAction(self._help_action)

        self._doc_action = QAction("View Documentation", self)
        self._doc_action.triggered.connect(self._on_doc_action)
        self.ui.cog_button.addAction(self._doc_action)

        self._reload_action = QAction("Reload", self)
        self._reload_action.triggered.connect(self._on_reload_action)
        self.ui.cog_button.addAction(self._reload_action)

        #################################################
        # set up preset tabs and load and init tree views
        self._entity_presets = {}
        self._current_entity_preset = None

        self._load_entity_presets()

        # load visibility state for details pane
        show_details = self._settings_manager.retrieve("show_details", False)
        self._set_details_pane_visiblity(show_details)

        # trigger an initial evaluation of filter proxy model
        self._apply_type_filters_on_publishes()
        #################################################
        # Sync
        self._files_to_sync = []
        #################################################
        # Publishing
        self._home_dir = None
        self._publish_files_path = None
        self._publish_files_description = None
        self._create_publisher_dir()
        self._sg_data = []

        self._submitted_data_to_publish = []
        self._pending_data_to_publish = []
        self._fstat_dict = {}
        self._action_data_to_publish = []
        self.publish_files_ui = PublishFilesUI(self, self.window())
        self._submitted_publish_list = []
        self._pending_publish_list = []
        self._change_dict = {}

                #################################################
        self._root_path = self._app.sgtk.roots.get('primary', None)
        # logger.debug("root_path:{}".format(self._root_path))
        self._drive = "Z:"
        if self._root_path:
            self._drive = self._root_path[0:2]

        # "delete" change
        self.default_changelist = self._p4.fetch_change()
        # self.default_changelist = "0"
        self._actions_change = self.default_changelist.get("Change")
        # self._actions_change = create_change(self._p4, "Perform actions")
        #################################################
        # Set logger
        self._set_logger()
        #logger.debug("This is a DEBUG message")
        #logger.info("This is an INFO message")
        #logger.warning("This is a WARNING message")
        #logger.error("This is an ERROR message")
        #################################################
        # Perforce data
        self.action_dict = {
            "add": "add",
            "move/add": "add",
            "delete": "delete",
            "edit": "edit"
        }
        self.status_dict = {
            "add": "p4add",
            "move/add": "p4add",
            "delete": "p4del",
            "edit": "p4edit"
        }
        self.settings = {
            "wire": "Alias File",
            "abc": "Alembic Cache",
            "max": "3dsmax Scene",
            "hrox": "NukeStudio Project",
            "hip": "Houdini Scene",
            "hipnc": "Houdini Scene",
            "hiplc": "Houdini Scene",
            "ma": "Maya Scene",
            "mb": "Maya Scene",
            "fbx": "Motion Builder FBX",
            "nk": "Nuke Script",
            "psd": "Photoshop Image",
            "psb": "Photoshop Image",
            "vpb": "VRED Scene",
            "vpe": "VRED Scene",
            "osb": "VRED Scene",
            "dpx": "Rendered Image",
            "exr": "Rendered Image",
            "tiff": "Texture",
            "tx": "Texture",
            "tga": "Texture",
            "dds": "Texture",
            "jpeg": "Image",
            "jpg": "Image",
            "mov": "Movie",
            "mp4": "Movie",
            "pdf": "PDF",
            "png": "Image File",
            "spp": "PhotoPlus Image",
            "ztl": "ZBrush Document",
            "json": "JSON File",
            "pkl": "Python Pickle",
            "aep": " Adobe After Effects",
            "webm": "WebM Format",
        }
        ##########################################################################################
        # Filesystem for cureent user tasks:
        # Create a QTimer with a single-shot connection
        # Initialize a flag to track whether the function has been executed
        try:
            self._function_executed = False

            # Create a QTimer
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._run_function_once)

            # Delay the execution for 1 second (you can adjust the delay as needed)
            self.timer.start(5000)
        except Exception as e:
            logger.debug(e)
            pass

        ##########################################################################################
        self.submitter_widget = None
        ##########################################################################################

    def _set_logger(self):
        sg_log_handler = ShotGridLogHandler(self.ui.log_window)
        sg_log_handler.setFormatter(logging.Formatter('%(message)s'))

        # Add to 'sgtk' logger only
        sgtk_logger = logging.getLogger("sgtk")
        sgtk_logger.setLevel(logging.DEBUG)
        if not any(isinstance(h, ShotGridLogHandler) for h in sgtk_logger.handlers):
            sgtk_logger.addHandler(sg_log_handler)

        # Let children like `sgtk.platform.get_logger(__name__)` inherit this
        sgtk_logger.propagate = True

    def _set_logger_10(self):
        logger = sgtk.platform.get_logger(__name__)
        logger.setLevel(logging.DEBUG)

        # Avoid adding duplicate handlers
        if not any(isinstance(h, ShotGridLogHandler) for h in logger.handlers):
            sg_log_handler = ShotGridLogHandler(self.ui.log_window)
            sg_log_handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(sg_log_handler)

    def _set_logger_Original(self):
        # Create custom log handler and add it to the ShotGrid logger
        sg_log_handler = ShotGridLogHandler(self.ui.log_window)
        # sg_log_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        sg_log_handler.setFormatter(logging.Formatter('%(message)s'))
        logger = sgtk.platform.get_logger(__name__)
        logger.addHandler(sg_log_handler)
        logger.setLevel(logging.DEBUG)

        sgtk_logger = logging.getLogger("sgtk")
        sgtk_logger.addHandler(sg_log_handler)
        sgtk_logger.setLevel(logging.DEBUG)

        # Simulate some log messages
        #logger.info("Color codes:")
        #logger.debug("Debug message")
        #logger.info("Info message")
        #logger.warning("Warning message")
        #logger.error("Error message")
        #logger.critical("Critical message")

    def _set_logger_new(self):
        # Create custom log handler and add it to the ShotGrid logger
        sg_log_handler = ShotGridLogHandler(self.ui.log_window)
        sg_log_handler.setFormatter(logging.Formatter('%(message)s'))

        # Attach the custom handler to all relevant loggers
        # Root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(sg_log_handler)
        root_logger.setLevel(logging.DEBUG)

        # ShotGrid logger
        sg_logger = sgtk.platform.get_logger(__name__)
        sg_logger.addHandler(sg_log_handler)
        sg_logger.setLevel(logging.DEBUG)

        # Iterate over all existing loggers and attach the handler
        for logger_name in logging.root.manager.loggerDict:
            logger = logging.getLogger(logger_name)
            logger.addHandler(sg_log_handler)
            logger.setLevel(logging.DEBUG)

        # Optional: Remove other handlers if you want to only show logs in your custom handler
        for handler in root_logger.handlers[:]:
            if handler != sg_log_handler:
                root_logger.removeHandler(handler)

        # Simulate some log messages for testing
        sg_logger.info("Color codes:")
        sg_logger.debug("Debug message")
        sg_logger.info("Info message")
        sg_logger.warning("Warning message")
        sg_logger.error("Error message")
        sg_logger.critical("Critical message")

    def add_dropped_files_to_changelist(self, changelist_id, files_data):
        """Adds processed dropped files to the specified changelist data."""
        if changelist_id not in self._change_dict:
            # Handle case where the changelist might not exist yet (e.g., 'default' might need init)
            # For simplicity, assuming 'default' always exists or is created if needed
             if changelist_id == 'default' and 'default' not in self._change_dict:
                 self._get_default_changelists() # Ensure default exists
             else:
                logger.error(f"Target changelist '{changelist_id}' not found in internal data.")
                return

        for file_info in files_data:
            sg_item = file_info['sg_item']
            action = file_info['action']

            # Add necessary fields for the pending view model
            sg_item['action'] = action # Ensure action is set
            sg_item['headChange'] = changelist_id # Associate with the target changelist

            # Append to the list for that changelist
            # Avoid duplicates if the file was already somehow in the list
            depot_file = sg_item.get('depotFile')
            if depot_file:
                 is_duplicate = any(item.get('depotFile') == depot_file for item in self._change_dict[changelist_id] if 'depotFile' in item)
                 if not is_duplicate:
                      self._change_dict[changelist_id].append(sg_item)
                 else:
                      logger.debug(f"Skipping duplicate add for {depot_file} in changelist {changelist_id}")
            else:
                 # Handle cases without depotFile if necessary, though unlikely for 'add'
                 self._change_dict[changelist_id].append(sg_item)

        logger.debug(f"Added {len(files_data)} files to changelist '{changelist_id}' data.")


    def _get_shotgun_panel_widget(self):
        # Get the current engine
        engine = sgtk.platform.current_engine()
        if not engine:
            logger.error("No current engine found. This code must be run within a Toolkit environment.")
        else:
            #logger.debug("Current engine name: {}".format(engine.name))

            # Retrieve the desired app, e.g., the Shotgun Panel app
            shotgun_panel_app = engine.apps.get("tk-multi-shotgunpanel")

            if shotgun_panel_app:
                #logger.debug("Shotgun Panel app is loaded.")
                try:
                    # Use create_widget_for_P4SG() to get the panel widget without creating a new window.
                    if not self.shotgun_panel_widget:
                        self.shotgun_panel_widget = shotgun_panel_app.create_widget_for_P4SG(self.ui.panel_details)

                    if self.shotgun_panel_widget:
                        # logger.debug(">>>>> entity_data {}".format(self._entity_data))
                        if self._entity_data:
                            self._entity_path, entity_id, entity_type = self._get_entity_info(self._entity_data)
                            if entity_id and entity_type:
                                logger.debug("Navigate to entity ID # {}".format(entity_id))
                                self.shotgun_panel_widget.navigate_to_entity(entity_type, entity_id)

                        # Clear any existing widgets in the layout
                        while self.ui.panel_layout.count():
                            child = self.ui.panel_layout.takeAt(0)
                            if child.widget():
                                child.widget().setParent(None)  # Remove the widget from the layout without deleting it

                        # Add the panel widget to the layout
                        self.ui.panel_layout.addWidget(self.shotgun_panel_widget)
                        #logger.info("Shotgun panel widget added to the layout.")

                    else:
                        logger.error("Failed to retrieve the panel widget.")
                except Exception as e:
                    logger.error("Failed to create or add the Shotgun panel widget: {}".format(e))
            else:
                logger.warning("Shotgun Panel app is not loaded. Please check configuration.")

    def _run_function_once(self):
        try:
            # Check if the function has already been executed
            if not self._function_executed:
                # Call the function
                self._create_current_user_task_filesystem_structure()

                # Set the flag to True to indicate that the function has been executed
                self._function_executed = True
        except Exception as e:
            logger.debug(e)
            pass

    def on_show_event(self, event):
        # This method will be called when the widget is shown
        self._create_current_user_task_filesystem_structure()

        # call the base class implementation
        super().showEvent(event)

    def _show_publish_actions(self, pos):
        """
        Shows the actions for the current publish selection.

        :param pos: Local coordinates inside the viewport when the context menu was requested.
        """
        # Get the selected item
        selected_indexes = self.ui.publish_view.selectionModel().selectedIndexes()
        if not selected_indexes:
            return  # No selection, do not show menu

        model_index = selected_indexes[0]
        proxy_model = model_index.model()
        source_index = proxy_model.mapToSource(model_index)
        item = source_index.model().itemFromIndex(source_index)
        is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)

        # Build a menu with all the actions.
        menu = QMenu(self)

        if is_folder:
            # Add folder-specific actions
            menu.addAction(self._preview_create_folders_action)
            menu.addAction(self._create_folders_action)
            menu.addAction(self._unregister_folders_action)
        else:
            try:
                sg_item = shotgun_model.get_sg_data(model_index)

                # Find out if selected is a published file or not
                if sg_item:
                    # logger.debug(">>>> _show_publish_actions: sg_item: {}".format(sg_item))
                    is_published = sg_item.get("published_file_type", None)
                    logger.debug(">>>> _show_publish_actions: is_published: {}".format(is_published))
                    if is_published:
                        # Add non-folder-specific actions
                        menu.addAction(self._add_action)
                        menu.addAction(self._edit_action)
                        menu.addAction(self._delete_action)
                        menu.addSeparator()
                        menu.addAction(self._revert_action)
                        menu.addSeparator()
                        menu.addAction(self._refresh_action)
                    else:
                        menu.addAction(self._fix_action)
                        menu.addSeparator()
                        menu.addAction(self._revert_action)
                        menu.addSeparator()
                        menu.addAction(self._refresh_action)
            except Exception as e:
                logger.debug(">>>> _show_publish_actions: Error: {}".format(e))



        # Wait for the user to pick something.
        menu.exec_(self.ui.publish_view.mapToGlobal(pos))

    @property
    def selected_publishes(self):
        """
        Get the selected sg_publish details
        """
        # check to see if something is selected in the details file_history view:
        selection_model = self.ui.file_history_view.selectionModel()
        if selection_model.hasSelection():
            # only handle single selection atm
            proxy_index = selection_model.selection().indexes()[0]

            # the incoming model index is an index into our proxy model
            # before continuing, translate it to an index into the
            # underlying model
            source_index = proxy_index.model().mapToSource(proxy_index)

            # now we have arrived at our model derived from StandardItemModel
            # so let's retrieve the standarditem object associated with the index
            item = source_index.model().itemFromIndex(source_index)

            sg_data = item.get_sg_data()
            if sg_data:
                return [sg_data]

        sg_data_list = []

        # nothing selected in the details view so check to see if something is selected
        # in the main publish view:
        selection_model = self.ui.publish_view.selectionModel()
        if selection_model.hasSelection():

            for proxy_index in selection_model.selection().indexes():

                # the incoming model index is an index into our proxy model
                # before continuing, translate it to an index into the
                # underlying model
                source_index = proxy_index.model().mapToSource(proxy_index)

                # now we have arrived at our model derived from StandardItemModel
                # so let's retrieve the standarditem object associated with the index
                item = source_index.model().itemFromIndex(source_index)

                sg_data = item.get_sg_data()

                sg_data = item.get_sg_data()
                if sg_data and not item.data(SgLatestPublishModel.IS_FOLDER_ROLE):
                    sg_data_list.append(sg_data)

        return sg_data_list

    def closeEvent(self, event):
        """
        Executed when the main dialog is closed.
        All worker threads and other things which need a proper shutdown
        need to be called here.
        """
        # display exit splash screen
        splash_pix = QPixmap(":/res/exit_splash.png")
        splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        splash.setMask(splash_pix.mask())
        splash.show()
        QCoreApplication.processEvents()

        try:
            # clear the selection in the main views.
            # this is to avoid re-triggering selection
            # as items are being removed in the models
            #
            # note that we pull out a fresh handle to the selection model
            # as these objects sometimes are deleted internally in the view
            # and therefore persisting python handles may not be valid
            self.ui.file_history_view.selectionModel().clear()
            self.ui.publish_view.selectionModel().clear()

            # disconnect some signals so we don't go all crazy when
            # the cascading model deletes begin as part of the destroy calls
            for p in self._entity_presets:
                self._entity_presets[
                    p
                ].view.selectionModel().selectionChanged.disconnect(
                    self._reload_treeview
                )

            # gracefully close all connections
            shotgun_globals.unregister_bg_task_manager(self._task_manager)
            self._task_manager.shut_down()

        except:
            app = sgtk.platform.current_bundle()
            app.log_exception("Error running Loader App closeEvent()")

        # close splash
        splash.close()

        # okay to close dialog
        event.accept()

    def is_first_launch(self):
        """
        Returns true if this is the first time UI is being launched
        """
        ui_launched = self._settings_manager.retrieve(
            "ui_launched", False, self._settings_manager.SCOPE_ENGINE
        )
        if ui_launched == False:
            # store in settings that we now have launched
            self._settings_manager.store(
                "ui_launched", True, self._settings_manager.SCOPE_ENGINE
            )

        return not (ui_launched)

    ########################################################################################
    # info bar related
    def _get_default_changelists(self):
        default_changelist = self._p4.fetch_change()
        key = "default"
        self._change_dict[key] = []
        sg_item = {}
        sg_item['changeListInfo'] = True
        sg_item['headTime'] = default_changelist.get('time', None)
        sg_item['p4_user'] = default_changelist.get('User', None)
        description = default_changelist.get('Description', None)
        if not description or "description" in description:
            description = "Default Changelist"
        sg_item['description'] = description
        self._change_dict[key].append(sg_item)

        # logger.debug("<<<<<<<  default_changelist: {}".format(default_changelist))
        if default_changelist:
            depot_files = default_changelist.get('Files', None)
            if depot_files:
                for depot_file in depot_files:
                    if depot_file:


                        fstat_list = self._p4.run("fstat", depot_file)
                        if fstat_list:
                            sg_item = fstat_list[0]
                            sg_item['description'] = default_changelist.get("Description", None)
                            sg_item['p4_user'] = default_changelist.get('User', None)
                            sg_item['client'] = default_changelist.get('client', None)
                            sg_item['time'] = default_changelist.get('time', None)
                            # sg_item['change'] = default_changelist.get('Change', None)
                            # sg_item['status'] = default_changelist.get("Status", None)
                            # sg_item['Published'] = False

                            file_path = sg_item.get("clientFile", None)
                            if file_path:
                                sg_item["path"] = {}
                                sg_item["path"]["local_path"] = file_path
                            #    sg_item["name"] = os.path.basename(file_path)
                            have_rev = sg_item.get('haveRev', "0")
                            head_rev = sg_item.get('headRev', "0")
                            if not have_rev or have_rev == "none":
                                have_rev = "0"
                            sg_item["revision"] = "#{}/{}".format(have_rev, head_rev)
                            sg_item["action"] = sg_item.get("action", None) or sg_item.get("headAction", None)

                            #  sg_item["code"] = "{}#{}".format(sg_item.get("name", None), head_rev)
                            p4_status = self._get_action(sg_item)
                            #sg_item["sg_status_list"] = self._get_p4_status(p4_status)

                            #sg_item["depot_file_type"] = self._get_publish_type(file_path)

                            self._change_dict[key].append(sg_item)




            # logger.debug("key {}:{}".format(key, self._change_dict[key]))

    def _get_pending_changelists(self):

        client = self._p4.fetch_client()
        workspace = client.get("Client", None)
        # Get the pending changelists
        change_lists = self._p4.run_changes("-l", "-s", "pending", "-c", workspace)
        # logger.debug("<<<<<<<  change_lists: {}".format(change_lists))

        for change_list in change_lists:
            key = change_list.get("change", None)
            #logger.debug("{}".format(key))
            desc_files = self._p4.run("describe", "-O", key)
            # logger.debug(">>>> desc_files: {}".format(depot_file))
            if desc_files:

                for desc in desc_files:
                    # logger.debug(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> desc_file: {}".format(desc))
                    depot_files = desc.get('depotFile', None)

                    if depot_files:
                        if key not in self._change_dict:
                            self._change_dict[key] = []
                        sg_item = {}
                        sg_item['changeListInfo'] = True
                        sg_item['headTime'] = change_list.get('time', None)
                        sg_item['p4_user'] = change_list.get('user', None)
                        sg_item['description'] = change_list.get('desc', None)
                        sg_item['client'] = change_list.get('client', None)
                        sg_item['time'] = change_list.get('time', None)
                        # Add info sg_item
                        self._change_dict[key].append(sg_item)

                        files_rev = desc.get('rev', None)
                        files_action = desc.get('action', None)
                        change_file_info = zip(depot_files, files_rev, files_action)

                        for depot_file, rev, action in change_file_info:
                            if depot_file:
                                fstat_list = self._p4.run("fstat", depot_file)
                                if fstat_list:
                                    fstat = fstat_list[0]
                                    client_file = self._get_client_file(depot_file)
                                    if client_file:
                                        sg_item = {}
                                        sg_item["depotFile"] = depot_file
                                        sg_item["path"] = {}
                                        sg_item["path"]["local_path"] = client_file
                                        sg_item["headRev"] = fstat.get("headRev", "0")
                                        sg_item["haveRev"] = fstat.get("haveRev", "0")
                                        if not sg_item["haveRev"] or sg_item["haveRev"] == "none":
                                            sg_item["haveRev"] = "0"
                                        sg_item["revision"] = "#{}/{}".format(sg_item["haveRev"], sg_item["headRev"])
                                        sg_item["action"] = action
                                        sg_item["headChange"] = key
                                        self._change_dict[key].append(sg_item)


            #logger.debug("key {}:{}".format(key, self._change_dict[key]))

    def _get_client_file(self, depot_file):
        """
        Convert depot path to local path
        For example, convert:
        "//Ark2Depot/Content/Base/Characters/Human/Survivor/Armor/Cloth_T3/_ven/MDL/Survivor_M_Armor_Cloth_T3_MDL.fbx"
        to:
        'B:\Ark2Depot\Content\Base\Characters\Human\Survivor\Armor\Cloth_T3\_ven\MDL\Survivor_M_Armor_Cloth_T3_MDL.fbx'
        """
        client_file = None
        try:
            if depot_file:
                #depot_file.replace("//", "\\")
                #depot_file.replace("/", "\\")
                client_file = "{}{}".format(self._drive, depot_file)
        except:
            pass
        return client_file

    def _get_pending_publish_data(self):
        if self._pending_publish_list:
            for publish_item in self._pending_publish_list:
                if publish_item:
                    sg_item = publish_item[0]
                    # is_published = sg_item.get("Published", None)
                    # if not is_published:
                    publish_checkbox = publish_item[2]
                    if publish_checkbox.isChecked():
                        self._pending_data_to_publish.append(sg_item)

    def _get_submitted_publish_data(self):
        if self._submitted_publish_list:
            for publish_item in self._submitted_publish_list:
                if publish_item:
                    sg_item = publish_item[0]
                    is_published = sg_item.get("Published", None)
                    if not is_published:
                        publish_checkbox = publish_item[2]
                        if publish_checkbox.isChecked():
                            self._submitted_data_to_publish.append(sg_item)


    def _create_perforce_ui(self, data_dict, sorted=None):
        # publish list
        publish_widget = QWidget()
        publish_layout = QVBoxLayout()

        publish_list = self._create_publish_layout(data_dict, sorted)

        current_publish = ''
        for publish_item in publish_list:
            if publish_item:
                if publish_item[3] != current_publish:
                    sg_item = publish_item[0]
                    info_layout = QHBoxLayout()
                    info_layout.layout().setContentsMargins(0, 15, 0, 5)

                    change_label = QLabel()
                    change_label.setMinimumWidth(120)
                    change_label.setMaximumWidth(120)
                    change_txt = self._get_change_list_info(sg_item)
                    change_label.setText(change_txt)

                    publish_time_label = QLabel()
                    publish_time_label.setMinimumWidth(200)
                    publish_time_label.setMaximumWidth(200)
                    publish_time_txt = self._get_publish_time_info(sg_item)
                    publish_time_label.setText(publish_time_txt)

                    user_name_label = QLabel()
                    user_name_label.setMinimumWidth(150)
                    user_name_label.setMaximumWidth(150)
                    user_name_txt = self._get_user_name_info(sg_item)
                    user_name_label.setText(user_name_txt)

                    description_label = QLabel()
                    description_label.setMinimumWidth(400)
                    description_label.setMaximumWidth(2000)
                    description_txt = self._get_description_info(sg_item)
                    description_label.setText(description_txt)

                    info_layout.addWidget(change_label)
                    info_layout.addWidget(publish_time_label)
                    info_layout.addWidget(user_name_label)
                    info_layout.addWidget(description_label)
                    #logger.debug("<<<<<<<  sg_item is: {}".format(sg_item))

                    is_published = sg_item.get("Published", None)
                    #logger.debug("<<<<<<<  sg_item published is: {}".format(is_published))
                    if is_published:
                        info_layout.setEnabled(False)
                    publish_layout.addLayout(info_layout)

                    current_publish = publish_item[3]
            publish_layout.addLayout(publish_item[1])
        publish_widget.setLayout(publish_layout)

        for publish in publish_list:
            if publish:
                publish_layout.addLayout(publish[1])
        publish_widget.setLayout(publish_layout)


        return publish_widget, publish_list
        # Submitted Scroll Area
        # self.ui.submitted_scroll.setWidget(publish_widget)
        #self.ui.submitted_scroll.setVisible(True)

    def _setup_column_view_model(self, root):
        """
        Create the model and proxy model required by a Perforce .

        :param root: The path to the root of the Shotgun hierarchy to display.
        :return: Created `(proxy model)`.
        """

        # Construct the hierarchy model and load a hierarchy that leads
        # to entities that are linked via the "PublishedFile.entity" field.
        model = SgHierarchyModel(
            self,
            root_entity=root,
            bg_task_manager=self._task_manager,
            include_root=None,
        )

        # Create a proxy model.
        proxy_model = QtGui.QSortFilterProxyModel(self)
        proxy_model.setSourceModel(model)

        # Impose and keep the sorting order on the default display role text.
        proxy_model.sort(0)
        proxy_model.setDynamicSortFilter(True)

        # When clicking on a node, we fetch all the nodes under it so we can populate the
        # right hand-side. Make sure we are notified when the child come back so we can load
        # publishes for the current item.
        model.data_refreshed.connect(self._hierarchy_refreshed)

        return (model, proxy_model)

    def _create_publish_layout(self, data_dict, sorted):
        publish_list = []
        if not sorted:
            node_dictionary = self._get_change_dictionary(data_dict)
        else:
            node_dictionary = data_dict
        #logger.debug("<<<<<<<  node_dictionary: {}".format(node_dictionary))
        for key in node_dictionary.keys():
            if key:
                # logger.debug("<<<<<<<  key: {}".format(key))
                publish_label = QLabel()
                publish_label.setText(str(key))
                for sg_item in node_dictionary[key]:
                    if sg_item:
                        # logger.debug("<<<<<<<  sg_item: {}".format(sg_item))
                        # depot_path = self._get_depot_path(sg_item)
                        depot_path = sg_item.get("depotFile", None)
                        is_published = sg_item.get("Published", None)

                        action = self._get_action(sg_item)

                        publish_layout = QHBoxLayout()
                        publish_checkbox = QCheckBox()
                        if is_published:
                            publish_checkbox.setChecked(True)

                        action_line_edit = QLineEdit()
                        action_line_edit.setMinimumWidth(80)
                        action_line_edit.setMaximumWidth(80)
                        action_line_edit.setText('{}'.format(action))
                        # action_line_edit.setEnabled(False)

                        publish_path_line_edit = QLineEdit()
                        publish_path_line_edit.setMinimumWidth(750)
                        publish_path_line_edit.setText('{}'.format(depot_path))
                        # publish_path_line_edit.setEnabled(False)

                        publish_layout.addWidget(publish_checkbox)
                        publish_layout.addWidget(action_line_edit)
                        publish_layout.addWidget(publish_path_line_edit)

                        if is_published:
                            publish_checkbox.setEnabled(False)
                            action_line_edit.setEnabled(False)
                            publish_path_line_edit.setEnabled(False)
                        else:
                            msg = "<span style='color:#2C93E2'>Check files in the Pending view then click <i>Submit Files</i>to publish them using the <i>Shotgrid Publisher</i>...</span>"
                            publish_checkbox.setToolTip(msg)
                            publish_path_line_edit.setToolTip(msg)


                        publish_list.append((sg_item, publish_layout, publish_checkbox, key))
        return publish_list

    def _get_change_list_info(self, sg_item):
        """
        Get change list info
        """
        change_txt = ""
        change_list = sg_item.get("change", None)
        if not change_list:
            change_list = sg_item.get("headChange", None)
        if change_list:
            change_txt += "<span style='color:#2C93E2'><B>Change List: </B></span>"
            change_txt += "<span><B>{}   </B></span> ".format(change_list)
            # change_txt += "   \t"
        return change_txt

    def _get_publish_time_info(self, sg_item):
        publish_time_txt = ""

        publish_time = self._get_publish_time(sg_item)
        if publish_time:
            publish_time_txt += "<span style='color:#2C93E2'><B>Creation Time: </B></span>"
            publish_time_txt += "<span><B>{}   </B></span>".format(publish_time)
        return publish_time_txt

    def _get_user_name_info(self, sg_item):
        user_name_txt = ""

        user_name = self._get_publish_user(sg_item)
        if user_name:
            user_name_txt += "<span style='color:#2C93E2'><B>User: </B></span>"
            user_name_txt += "<span><B>{}   </B></span>\t\t".format(user_name)
        return user_name_txt

    def _get_description_info(self, sg_item):
        description_txt = ""

        description = sg_item.get("description", None)
        if description:
            description_txt += "<span style='color:#2C93E2'><B>Description: </B></span>"
            description_txt += "<span><B>{}</B></span>\t\t".format(description)

        return description_txt


    def _get_publish_time(self, sg_item):
        publish_time= None
        dt = sg_item.get("headTime", None)
        # logger.debug(">>>>> dt is: {}".format(dt))
        if dt:
            publish_time = create_publish_timestamp(dt)
        return publish_time

    def _get_publish_user(self, sg_item):
        publish_user, user_name = None, None

        p4_user = sg_item.get("p4_user", None)
        if p4_user:
            publish_user = self._app.shotgun.find_one('HumanUser',
                                              [['sg_p4_user', 'is', p4_user]],
                                              ["id", "type", "email", "login", "name", "image"])
        # logger.debug(">>> Publish user is: {}".format(publish_user))
        if not publish_user:
            action_owner = sg_item.get("actionOwner", None)
            if action_owner:
                publish_user = self._app.shotgun.find_one('HumanUser',
                                                     [['sg_p4_user', 'is', action_owner]],
                                                     ["id", "type", "email", "login", "name", "image"])
        # logger.debug(">>>> Publish user is: {}".format(publish_user))
        if not publish_user:
            publish_user = login.get_current_user(self._app.sgtk)

        # logger.debug(">>>>> Publish user is: {}".format(publish_user))
        if publish_user:
            user_name = publish_user.get("name", None)

        return user_name

    def _get_change_dictionary(self, data_dict):
        """
        Creates dictionary for every changelist and all its depot files
        key: changelist number
        value: sorted list of depotfiles
        :return: dictionary
        """
        change_dict = {}

        if data_dict:
            for sg_item in data_dict.values():
                if sg_item:
                    key = sg_item.get("headChange", None)
                    if key:
                        if key not in change_dict:
                            change_dict[key] = []
                        change_dict[key].append(sg_item)

        change_dict_sorted = OrderedDict(sorted(change_dict.items()))

        # for key in change_dict_sorted:
        #   change_dict_sorted[key] = sorted(change_dict_sorted[key])
        # print(change_dict_sorted)
        return change_dict_sorted

    def _get_action(self, sg_item):
        """
        Get action
        """
        action = sg_item.get("action", None)
        if not action:
            action = sg_item.get("headAction", None)
        return action

    def _get_depot_path(self, sg_item):
        """
        Get depot path
        """
        depot_file = sg_item.get("depotFile", None)
        head_rev = sg_item.get("headRev", None)
        if head_rev:
            depot_file = "{}#{}".format(depot_file, head_rev)
        return depot_file

    def _on_file_history_selection(self, selected, deselected):
        """
        Called when the selection changes in the file_history view in the details panel

        :param selected:    Items that have been selected
        :param deselected:  Items that have been deselected
        """
        # emit the selection_changed signal
        self.selection_changed.emit()

    def _on_file_history_double_clicked(self, model_index):
        """
        When someone double clicks on a publish in the file_history view, run the
        default action

        :param model_index:    The model index of the item that was double clicked
        """
        # the incoming model index is an index into our proxy model
        # before continuing, translate it to an index into the
        # underlying model
        proxy_model = model_index.model()
        source_index = proxy_model.mapToSource(model_index)

        # now we have arrived at our model derived from StandardItemModel
        # so let's retrieve the standarditem object associated with the index
        item = source_index.model().itemFromIndex(source_index)

        # Run default action.
        sg_item = shotgun_model.get_sg_data(model_index)
        default_action = self._action_manager.get_default_action_for_publish(
            sg_item, self._action_manager.UI_AREA_HISTORY
        )
        if default_action:
            default_action.trigger()

    def _on_column_view_set_search_query(self, search_filter):
        # Chech if we are in Column view mode
        if self.main_view_mode == self.MAIN_VIEW_COLUMN:
            logger.debug("search_filter: {}".format(search_filter))
            if len(search_filter) > 1:
                self._column_view_search_filter = search_filter
            else:
                self._column_view_search_filter = None
            self._set_column_group()

    def _on_publish_filter_clicked(self):
        """
        Executed when someone clicks the filter button in the main UI
        """
        if self.ui.search_publishes.isChecked():
            self.ui.search_publishes.setIcon(
                QIcon(QPixmap(":/res/search_active.png"))
            )
            self._search_widget.enable()
            # Chech if we are in Column view mode
            if self.main_view_mode == self.MAIN_VIEW_COLUMN:
                # log search string from self.ui.search_publishes
                logger.debug("Column view mode, search is active")
        else:
            self.ui.search_publishes.setIcon(
                QIcon(QPixmap(":/res/search.png"))
            )
            self._search_widget.disable()
            if self.main_view_mode == self.MAIN_VIEW_COLUMN:
                # log search string from self.ui.search_publishes
                logger.debug("Column view mode, search is disabled")
                self._column_view_search_filter = None
                self._set_column_group()


    def _on_thumbnail_mode_clicked(self):
        """
        Executed when someone clicks the thumbnail mode button
        """
        self._set_main_view_mode(self.MAIN_VIEW_THUMB)

    def _on_list_mode_clicked(self):
        """
        Executed when someone clicks the list mode button
        """
        self._set_main_view_mode(self.MAIN_VIEW_LIST)

    def _on_column_mode_clicked(self):
        """
        Executed when someone clicks the column mode button
        """
        self._set_main_view_mode(self.MAIN_VIEW_COLUMN)

    def _on_submitted_mode_clicked(self):
        """
        Executed when someone clicks the submitted mode button
        """
        self._set_main_view_mode(self.MAIN_VIEW_SUBMITTED)

    def _on_pending_mode_clicked(self):
        """
        Executed when someone clicks the pending mode button
        """
        self._set_main_view_mode(self.MAIN_VIEW_PENDING)

    def _set_main_view_mode(self, mode):
        """
        Sets up the view mode for the main view.

        :param mode: either MAIN_VIEW_LIST or MAIN_VIEW_THUMB
        """
        if mode == self.MAIN_VIEW_LIST:
            self._turn_all_modes_off()
            self.ui.publish_view.setVisible(True)
            self.ui.list_mode.setIcon(
                QIcon(QPixmap(":/res/mode_switch_card_active.png"))
            )
            self.ui.list_mode.setChecked(True)
            self.ui.thumbnail_mode.setIcon(
                QIcon(QPixmap(":/res/mode_switch_thumb.png"))
            )

            self.ui.publish_view.setViewMode(QListView.ListMode)
            self.ui.publish_view.setItemDelegate(self._publish_list_delegate)
            #self._show_thumb_scale(False)
            self.main_view_mode = self.MAIN_VIEW_LIST
            self.ui.sync_files.setEnabled(True)
            self.ui.sync_parents.setEnabled(True)
            self.ui.fix_selected.setEnabled(False)
            self.ui.fix_all.setEnabled(False)
            self.ui.submit_files.setEnabled(False)
            self.ui.refresh_button.setIcon(self.active_refresh_button_icon)
            self.ui.get_latest_button.setIcon(self.active_get_latest_button_icon)
            self.ui.submit_button.setIcon(self.inactive_submit_button_icon)
            self.ui.get_latest_button.setEnabled(True)
            self.ui.submit_button.setEnabled(False)


        elif mode == self.MAIN_VIEW_THUMB:
            self._turn_all_modes_off()
            self.ui.publish_view.setVisible(True)

            self.ui.list_mode.setIcon(
                QIcon(QPixmap(":/res/mode_switch_card.png"))
            )

            self.ui.thumbnail_mode.setIcon(
                QIcon(QPixmap(":/res/mode_switch_thumb_active.png"))
            )
            self.ui.thumbnail_mode.setChecked(True)
            self.ui.publish_view.setViewMode(QListView.IconMode)
            self.ui.publish_view.setItemDelegate(self._publish_thumb_delegate)
            self._show_thumb_scale(True)
            self.main_view_mode = self.MAIN_VIEW_THUMB
            self.ui.sync_files.setEnabled(True)
            self.ui.sync_parents.setEnabled(True)
            self.ui.fix_selected.setEnabled(False)
            self.ui.fix_all.setEnabled(False)
            self.ui.submit_files.setEnabled(False)
            self.ui.refresh_button.setIcon(self.active_refresh_button_icon)
            self.ui.get_latest_button.setIcon(self.active_get_latest_button_icon)
            self.ui.submit_button.setIcon(self.inactive_submit_button_icon)
            self.ui.get_latest_button.setEnabled(True)
            self.ui.submit_button.setEnabled(False)

        elif mode == self.MAIN_VIEW_COLUMN:
            self._turn_all_modes_off()
            self.ui.column_view.setVisible(True)
            #self.ui.perforce_scroll.setVisible(True)
            self.ui.column_mode.setIcon(self.active_column_view_icon)

            self.ui.column_mode.setChecked(True)

            self.main_view_mode = self.MAIN_VIEW_COLUMN
            self.ui.publish_view.setItemDelegate(self._publish_list_delegate)
            self._populate_column_view_widget()
            self.ui.sync_files.setEnabled(True)
            self.ui.sync_parents.setEnabled(True)
            self.ui.fix_selected.setEnabled(False)
            self.ui.fix_all.setEnabled(False)
            self.ui.submit_files.setEnabled(False)

            self.ui.refresh_button.setIcon(self.active_refresh_button_icon)
            self.ui.get_latest_button.setIcon(self.active_get_latest_button_icon)
            self.ui.submit_button.setIcon(self.inactive_submit_button_icon)
            self.ui.get_latest_button.setEnabled(True)
            self.ui.submit_button.setEnabled(False)

        elif mode == self.MAIN_VIEW_SUBMITTED:
            self._turn_all_modes_off()
            self.ui.submitted_scroll.setVisible(True)

            #self.ui.submitted_mode.setIcon(
            #    QIcon(QPixmap(":/res/mode_switch_card_active.png"))
            #)
            self.ui.submitted_mode.setIcon(self.submitted_icon)
            self.ui.submitted_mode.setChecked(True)

            self.main_view_mode = self.MAIN_VIEW_SUBMITTED
            self._populate_submitted_widget()
            self.ui.sync_files.setEnabled(False)
            self.ui.sync_parents.setEnabled(False)
            self.ui.fix_selected.setEnabled(True)
            self.ui.fix_all.setEnabled(True)
            self.ui.submit_files.setEnabled(False)
            self.ui.refresh_button.setIcon(self.active_refresh_button_icon)
            self.ui.get_latest_button.setIcon(self.inactive_get_latest_button_icon)
            self.ui.submit_button.setIcon(self.inactive_submit_button_icon)
            self.ui.get_latest_button.setEnabled(False)
            self.ui.submit_button.setEnabled(False)

        elif mode == self.MAIN_VIEW_PENDING:
            self._populate_pending_widget()
            self.ui.sync_files.setEnabled(False)
            self.ui.sync_parents.setEnabled(False)
            self.ui.fix_selected.setEnabled(False)
            self.ui.fix_all.setEnabled(False)
            self.ui.submit_files.setEnabled(True)
            self.ui.refresh_button.setIcon(self.active_refresh_button_icon)
            self.ui.get_latest_button.setIcon(self.inactive_get_latest_button_icon)
            self.ui.submit_button.setIcon(self.active_submit_button_icon)
            self.ui.get_latest_button.setEnabled(False)
            self.ui.submit_button.setEnabled(True)
        else:
            raise TankError("Undefined view mode!")

        self.ui.publish_view.selectionModel().clear()
        self._settings_manager.store("main_view_mode", mode)

    def _set_thump_view_mode(self):
        self._turn_all_modes_off()
        self.ui.publish_view.setVisible(True)

        self.ui.list_mode.setIcon(
            QIcon(QPixmap(":/res/mode_switch_card.png"))
        )

        self.ui.thumbnail_mode.setIcon(
            QIcon(QPixmap(":/res/mode_switch_thumb_active.png"))
        )
        self.ui.thumbnail_mode.setChecked(True)
        self.ui.publish_view.setViewMode(QListView.IconMode)
        self.ui.publish_view.setItemDelegate(self._publish_thumb_delegate)
        self._show_thumb_scale(True)
        self.main_view_mode = self.MAIN_VIEW_THUMB
        self.ui.sync_files.setEnabled(True)
        self.ui.sync_parents.setEnabled(True)
        self.ui.fix_selected.setEnabled(False)
        self.ui.fix_all.setEnabled(False)
        self.ui.submit_files.setEnabled(False)

    def _set_column_view_mode(self):
        self._turn_all_modes_off()
        self.ui.column_view.setVisible(True)
        # self.ui.perforce_scroll.setVisible(True)
        self.ui.column_mode.setIcon(self.active_column_view_icon)
        self.ui.column_mode.setChecked(True)

        self.main_view_mode = self.MAIN_VIEW_COLUMN
        self.ui.publish_view.setItemDelegate(self._publish_list_delegate)
        self._populate_column_view_widget()
        self.ui.sync_files.setEnabled(True)
        self.ui.sync_parents.setEnabled(True)
        self.ui.fix_selected.setEnabled(False)
        self.ui.fix_all.setEnabled(False)
        self.ui.submit_files.setEnabled(False)

    def _populate_pending_widget(self):
        msg = "\n <span style='color:#2C93E2'>Populating the pending view. Please wait...</span> \n"
        self._add_log(msg, 2)
        self._turn_all_modes_off()
        self.ui.pending_scroll.setVisible(True)
        self.ui.pending_mode.setIcon(self.pending_icon)
        # self.ui.pending_mode.setIcon(
        #    QIcon(QPixmap(":/res/mode_switch_card_active.png"))
        # )
        self.ui.pending_mode.setChecked(True)

        self.main_view_mode = self.MAIN_VIEW_PENDING

        self._change_dict = {}
        self._get_default_changelists()
        self._get_pending_changelists()

        # publish_widget, self._pending_publish_list = self._create_perforce_ui(self._change_dict, sorted=True)
        self.pending_tree_view = TreeViewWidget(data_dict=self._change_dict, sorted=True, mode="pending", p4=self._p4, parent=self)
        self.pending_tree_view.set_mode()
        self.pending_tree_view.single_selection()
        self.pending_tree_view.populate_treeview_widget_pending()
        self._pending_view_widget = self.pending_tree_view.get_treeview_widget()

        # Pending Scroll Area
        #self.ui.pending_scroll.setWidget(self._pending_view_widget)
        # Create a container widget for the TreeView
        container_widget = QWidget()
        container_layout = QVBoxLayout(container_widget)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Add the TreeView widget to the container layout
        self._pending_view_widget = self.pending_tree_view.get_treeview_widget()
        self.pending_tree_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_layout.addWidget(self._pending_view_widget)

        # Add a stretch to ensure proper resizing
        container_layout.addStretch()

        # Attach the container to the scroll area
        self.ui.pending_scroll.setWidget(container_widget)
        self.ui.pending_scroll.setWidgetResizable(True)
        self.ui.pending_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ui.pending_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._pending_view_model = self.pending_tree_view.proxymodel
        self._create_pending_view_context_menu()

        msg = "\n <span style='color:#2C93E2'> Right-click on a file to 'Publish...' the changelist in Shotgrid or 'Revert' it in Perforce.</span> \n"

        #msg = "\n <span style='color:#2C93E2'>Choose the files you want to publish from the Pending view and then initiate the publishing process using the Shotgrid Publisher by clicking 'Submit Files'.</span> \n"
        self._add_log(msg, 2)
        self.ui.sync_files.setEnabled(False)
        self.ui.sync_parents.setEnabled(False)
        self.ui.fix_selected.setEnabled(False)
        self.ui.fix_all.setEnabled(False)
        self.ui.submit_files.setEnabled(True)

    def _set_perforce_buttons(self):
        """Sets the icons for the Perforce action buttons."""

        # --- Refresh Button ---
        icon_refresh = QIcon()
        # Attempt to load the pixmap
        pixmap_refresh = QPixmap(":/res/refresh_active_20.png")
        # Check if loading failed
        if pixmap_refresh.isNull():
            logger.error("Failed to load pixmap ':/res/refresh_active_20.png'")
            # Optionally set a fallback icon or leave it blank
            # self.ui.refresh_button.setIcon(QIcon()) # Example: Clear icon
        else:
            # Add the valid pixmap to the icon for the normal state
            icon_refresh.addPixmap(pixmap_refresh, QIcon.Normal, QIcon.Off)
            self.ui.refresh_button.setIcon(icon_refresh)
            logger.debug("Successfully set icon for refresh_button.")  # Optional success log

        # --- Get Latest Button ---
        icon_get_latest = QIcon()
        pixmap_get_latest = QPixmap(":/res/get_latest_active_20.png")
        if pixmap_get_latest.isNull():
            logger.error("Failed to load pixmap ':/res/get_latest_active_20.png'")
        else:
            icon_get_latest.addPixmap(pixmap_get_latest, QIcon.Normal, QIcon.Off)
            self.ui.get_latest_button.setIcon(icon_get_latest)
            logger.debug("Successfully set icon for get_latest_button.")  # Optional

        # --- Submit Button ---
        icon_submit = QIcon()
        pixmap_submit = QPixmap(":/res/submit_active_20.png")
        if pixmap_submit.isNull():
            logger.error("Failed to load pixmap ':/res/submit_active_20.png'")
        else:
            icon_submit.addPixmap(pixmap_submit, QIcon.Normal, QIcon.Off)
            self.ui.submit_button.setIcon(icon_submit)
            logger.debug("Successfully set icon for submit_button.")  # Optional

    def _set_perforce_buttons_original(self):

        self.ui.refresh_button.setIcon(
            #QIcon(QPixmap(":/res/tmp.png"))
            #QIcon(QPixmap(":/res/mode_switch_thumb_active.png"))
            QIcon(QPixmap(":/res/refresh_active_20.png"))
        )
        self.ui.get_latest_button.setIcon(
            QIcon(QPixmap(":/res/get_latest_active_20.png"))
        )
        self.ui.submit_button.setIcon(
            QIcon(QPixmap(":/res/submit_active_20.png"))
        )

    def _refresh_all(self):
        # logger.debug("Refreshing entity preset tabs...")
        # self.refresh_entity_preset_tabs()

        mode = self.main_view_mode
        if mode == self.MAIN_VIEW_LIST:
            logger.debug("Refreshing list view with updated data...")
            self._refresh_publish_area()
            #self.refresh_publish_data()
            #self._publish_model.async_refresh()
        elif mode == self.MAIN_VIEW_THUMB:
            logger.debug("Refreshing thumbnail view with updated publish data...")
            self._refresh_publish_area()
            #self.refresh_publish_data()
            #self._publish_model.async_refresh()
        elif mode == self.MAIN_VIEW_COLUMN:
            logger.debug("Refreshing column view with updated publish data...")
            self._refresh_column_view()
        elif mode == self.MAIN_VIEW_SUBMITTED:
            logger.debug("Refreshing submitted view with updated submit data...")
            self._refresh_submitted_view()
        elif mode == self.MAIN_VIEW_PENDING:
            logger.debug("Refreshing pending view with updated pending data...")
            self._refresh_pending_view()

    def _refresh_publish_area(self):
        """
        Hard reload all caches
        """
        msg = "\n <span style='color:#2C93E2'>Refreshing status model ...</span> \n"
        self._add_log(msg, 2)
        self._status_model.hard_refresh()
        msg = "\n <span style='color:#2C93E2'>Refreshing file history model ...</span> \n"
        self._add_log(msg, 2)
        self._publish_file_history_model.hard_refresh()
        msg = "\n <span style='color:#2C93E2'>Refreshing type model ...</span> \n"
        self._add_log(msg, 2)
        self._publish_type_model.hard_refresh()
        msg = "\n <span style='color:#2C93E2'>Refreshing publish model ...</span> \n"
        self._add_log(msg, 2)
        self._publish_model.hard_refresh()

        msg = "\n <span style='color:#2C93E2'>Refresh entity presets and sync count ...</span> \n"
        self._add_log(msg, 2)
        # for p in self._entity_presets:
        #    self._entity_presets[p].model.hard_refresh()
        self.refresh_entity_preset_tabs()
        msg = "\n <span style='color:#2C93E2'>Finally, clicking on the Home button...</span> \n"
        self._add_log(msg, 2)
        self._on_home_clicked()
        #self._load_entity_presets()
        #self._recreate_entity_presets()


    def _refresh_column_view(self):
        """
        Hard reload all caches
        """

        self._refresh_publish_area()
        msg = "\n <span style='color:#2C93E2'>Refreshing Column view ...</span> \n"
        self._add_log(msg, 2)
        self._populate_column_view_widget()

    def _refresh_submitted_view(self):
        """
        Hard reload all caches
        """

        self._refresh_publish_area()
        msg = "\n <span style='color:#2C93E2'>Refreshing Submitted view ...</span> \n"
        self._add_log(msg, 2)
        self._populate_submitted_widget()

    def _refresh_pending_view(self):
        """
        Hard reload all caches
        """

        self._refresh_publish_area()
        msg = "\n <span style='color:#2C93E2'>Refreshing Pending view ...</span> \n"
        self._add_log(msg, 2)
        self._populate_pending_widget()

    def refresh_entity_preset_tabs(self):
        """
        Refreshes the data displayed in the entity preset tabs, specifically
        updating the 'To Sync' count for the 'My Tasks' preset.
        """
        logger.debug("Refreshing entity preset tabs...")
        for preset_name, preset in self._entity_presets.items():
            if preset_name == "My Tasks":
                logger.debug("Refreshing 'My Tasks' preset tab.")
                view = preset.view
                proxy_model = preset.proxy_model
                source_model = proxy_model.sourceModel()

                # Ensure the model has the correct number of columns if it was somehow reset
                if source_model.columnCount() < 2:
                    source_model.setColumnCount(2)
                    source_model.setHorizontalHeaderLabels(["Name", "To Sync"])

                row_count = source_model.rowCount()
                logger.debug(f"Found {row_count} rows in 'My Tasks' model.")

                for row in range(row_count):
                    proxy_index = proxy_model.index(row, 0)
                    if not proxy_index.isValid():
                        # logger.debug(f"[REFRESH] Row {row}: Invalid proxy index")
                        continue

                    source_index = proxy_model.mapToSource(proxy_index)
                    if not source_index.isValid():
                        # logger.debug(f"[REFRESH] Row {row}: Invalid source index")
                        continue

                    # Get item using source_index.model()
                    item_model = source_index.model()
                    item = item_model.itemFromIndex(source_index)

                    if not item:
                        # logger.debug(f"[REFRESH] Row {row}: No item in model")
                        continue

                    # Extract the Shotgun data and field value from the node item.
                    (sg_data, entity_data) = model_item_data.get_item_data(item)

                    entity_path, entity_id, entity_type = self._get_entity_info(entity_data)
                    if not entity_id or not entity_type or not entity_path:
                        # logger.debug(
                        #    f"[REFRESH] Row {row}: Invalid entity info — Path: {entity_path}, ID: {entity_id}, Type: {entity_type}")
                        # Ensure the second column exists even if entity info is bad
                        if source_model.item(source_index.row(), 1) is None:
                            source_model.setItem(source_index.row(), 1, QStandardItem("N/A"))
                        continue

                    #logger.debug(f"[REFRESH] Row {row}: Entity Path: {entity_path}")
                    sync_count = self._get_sync_count_for_entity(entity_path)
                    #logger.debug(f"[REFRESH] Row {row}: Sync count = {sync_count}")

                    # Set value into the second column
                    if sync_count == 0:
                        msg = "Up to date"
                    else:
                        msg = "{} To Sync".format(sync_count)

                    # Get or create the item for the second column
                    desc_item = source_model.item(source_index.row(), 1)
                    if desc_item is None:
                        desc_item = QStandardItem()
                        source_model.setItem(source_index.row(), 1, desc_item)

                    desc_item.setText(str(msg))  # Update text
                    sync_icon = self.sync_icons.get_sync_pixmap(sync_count)
                    if sync_icon:
                        desc_item.setIcon(sync_icon)  # Update icon
                    else:
                        desc_item.setIcon(QIcon())  # Clear icon if none

                logger.debug("Finished refreshing 'My Tasks' preset tab.")
                # Trigger layout change to ensure the view updates visually
                #source_model.layoutChanged.emit()
                # view.update()  # <--- Removed this line
                break  # Stop after refreshing 'My Tasks'
        QCoreApplication.processEvents()
        logger.debug("Entity preset tabs refresh complete.")

    def _get_latest(self):
        logger.debug("Getting latest...")
        self._on_sync_current()
        ##self._on_sync_files()
        #self._on_sync_parents()
        self.refresh_entity_preset_tabs()

    def _submit_pending(self):
        logger.debug("Submitting pending...")
        self._on_submit_files()

    def _on_sync_current_2(self):
        """
        Finds the currently selected entity, determines its Perforce depot path,
        and syncs the files within that path that need updating.
        """
        logger.info("Starting sync for the current selection...")
        # logger.info(f"Entity data {self._entity_data}")
        # logger.info(f"Entity path {self._entity_path}")

        entity_path, entity_id, entity_type = self._get_selected_entity_path_info()
        logger.info(f"Selected Entity path {entity_path}")
        # logger.info(f">> Selected Entity id: {entity_id}")
        # logger.info(f">> Selected type id: {entity_type}")

        if not entity_path:
            logger.warning("No valid path found for the selected entity.")
            self._add_log(
                "\n <span style='color:#FFD700'>No valid path found for the selected entity.</span> \n", 2)
            return

        # Convert local path to Perforce depot path
        depot_path_base = self._convert_local_to_depot(entity_path)
        if not depot_path_base:
            logger.error(f"Could not convert local path '{entity_path}' to a Perforce depot path.")
            self._add_log(
                f"\n <span style='color:#CC3333'>Error: Could not map '{entity_path}' to a Perforce path.</span> \n", 2)
            return

        # Build Perforce wildcard path
        depot_path_wildcard = depot_path_base.rstrip('/') + '/...'
        logger.info(f"[SYNC CHECK] Running dry-run sync on: {depot_path_wildcard}")
        # Dry-run to get file count
        sync_output = self._p4.run_sync("-n", depot_path_wildcard)
        depot_files = [entry.get("depotFile") for entry in sync_output if "depotFile" in entry]
        num_files = len(depot_files)

        logger.info(f"Total files to sync: {num_files}")
        self._add_log(f"\n <span style='color:#2C93E2'>Found {num_files} files that need syncing.</span> \n", 2)

        if depot_files:
            logger.info("Files to sync:")
            for i, path in enumerate(depot_files, 1):
                logger.info(f"[{i:02}] {path}")
            sys.stdout.flush()
            sys.stderr.flush()
        else:
            logger.info("No individual depot files found in sync output.")

        progress_state = {"count": 0}

        def sync_thread_fn():
            try:
                # Run the actual Perforce sync using subprocess to get real-time output
                process = subprocess.Popen(
                    ["p4", "sync", depot_path_wildcard],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                file_re = re.compile(r"^([^#\s]+)#\d+ - .*")  # Matches depot file path

                for line in process.stdout:
                    line = line.strip()
                    if not line:
                        continue

                    logger.info(f"[p4] {line}")

                    match = file_re.match(line)
                    if match:
                        progress_state["count"] += 1
                        file_path = match.group(1)
                        msg = f"({progress_state['count']}/{num_files}) Syncing: {file_path}"
                        self._add_log(msg, 3)

                        progress = ((progress_state["count"]) / max(num_files, 1)) * 100
                        self._update_progress(progress)
                        QCoreApplication.processEvents()

                process.stdout.close()
                process.wait()

            except Exception as e:
                logger.error(f"Sync failed: {e}")
                self._add_log(
                    f"\n <span style='color:#CC3333'>Sync failed: {e}</span> \n", 2)

        # Launch thread to run sync
        sync_thread = threading.Thread(target=sync_thread_fn)
        sync_thread.start()

        self._add_log("\n <span style='color:#2C93E2'>Syncing files...</span> \n", 2)

        # Keep UI responsive while syncing
        while sync_thread.is_alive():
            QCoreApplication.processEvents()
            time.sleep(0.1)

        self._add_log(
            "\n <span style='color:#2C93E2'>Sync complete for current selection.</span> \n", 2)

        self._add_log("\n <span style='color:#2C93E2'>Reloading data...</span> \n", 2)
        self.refresh_publish_data()
        self.refresh_entity_preset_tabs()
        self._add_log("\n <span style='color:#2C93E2'>Reloading data is complete.</span> \n", 2)

    def _on_sync_current(self):
        """
        Finds the currently selected entity, determines its Perforce depot path,
        and syncs the files within that path that need updating.
        """
        logger.info("Starting sync for the current selection...")
        # logger.info(f"Entity data {self._entity_data}")
        # logger.info(f"Entity path {self._entity_path}")

        entity_path, entity_id, entity_type = self._get_selected_entity_path_info()
        logger.info(f"Selected Entity path {entity_path}")
        # logger.info(f">> Selected Entity id: {entity_id}")
        # logger.info(f">> Selected type id: {entity_type}")

        if not entity_path:
            logger.warning("No valid path found for the selected entity.")
            self._add_log(
                "\n <span style='color:#FFD700'>No valid path found for the selected entity.</span> \n", 2)
            return

        # Convert local path to Perforce depot path
        depot_path_base = self._convert_local_to_depot(entity_path)
        if not depot_path_base:
            logger.error(f"Could not convert local path '{entity_path}' to a Perforce depot path.")
            self._add_log(
                f"\n <span style='color:#CC3333'>Error: Could not map '{entity_path}' to a Perforce path.</span> \n", 2)
            return

        # Build Perforce wildcard path
        depot_path_wildcard = depot_path_base.rstrip('/') + '/...'
        logger.info(f"[SYNC CHECK] Running dry-run sync on: {depot_path_wildcard}")

        # Run dry-run sync to list files
        sync_output = self._p4.run_sync("-n", depot_path_wildcard)
        depot_files = [entry.get("depotFile") for entry in sync_output if "depotFile" in entry]
        num_files = len(depot_files)

        logger.info(f"Total files to sync: {num_files}")
        self._add_log(f"\n <span style='color:#2C93E2'>Found {num_files} files that need syncing.</span> \n", 2)

        if depot_files:
            logger.info("Files to sync:")
            for i, path in enumerate(depot_files, 1):
                msg = f"[{i:02}] {path}"
                self._add_log(msg, 3)
                # logger.info(f"[{i:02}] {path}")
            sys.stdout.flush()
            sys.stderr.flush()
        else:
            logger.info("No individual depot files found in sync output.")

        # Define sync logic in thread
        def sync_thread_fn():
            try:
                self._p4.run_sync(depot_path_wildcard)
            except Exception as e:
                logger.error(f"Sync failed: {e}")
                self._add_log(
                    f"\n <span style='color:#CC3333'>Sync failed: {e}</span> \n", 2)

        sync_thread = threading.Thread(target=sync_thread_fn)
        sync_thread.start()

        # Simulate progress bar
        if num_files > 0:
            for i in range(num_files):
                msg = f"({i + 1}/{num_files}) Syncing..."
                self._add_log(msg, 3)
                progress = ((i + 1) / num_files) * 100
                self._update_progress(progress)
                QCoreApplication.processEvents()
                time.sleep(0.15)
        else:
            self._update_progress(100)

        self._add_log("\n <span style='color:#2C93E2'>Finalizing file syncing, please wait...</span> \n", 2)

        # Wait for sync thread to finish
        while sync_thread.is_alive():
            QCoreApplication.processEvents()

        self._add_log(
            "\n <span style='color:#2C93E2'>Sync complete for current selection.</span> \n", 2)

        self._add_log("\n <span style='color:#2C93E2'>Reloading data...</span> \n", 2)
        #self.refresh_publish_data()
        # self.refresh_entity_preset_tabs()
        self._add_log("\n <span style='color:#2C93E2'>Reloading data is complete.</span> \n", 2)


    def _get_selected_entity_path_info(self):
        """
        Finds the currently selected entity in the active preset tab,
        determines its filesystem path, and returns relevant info.

        Handles cases where the selected item might be an intermediate node
        without a direct entity dictionary.

        :returns: Tuple (entity_path, entity_id, entity_type) or (None, None, None) if not found or not applicable.
        """
        logger.debug("Getting path info for selected entity...")

        selected_item = self._get_selected_entity()
        if not selected_item:
            logger.warning("No entity selected in the tree view.")
            self._add_log(
                "\n <span style='color:#FFD700'>No entity selected. Please select an item in the left panel.</span> \n",
                2)
            return None, None, None

        # Extract the Shotgun data and field value from the selected item
        # The second item returned ('field_value') might be a string for intermediate nodes
        (sg_data, field_value) = model_item_data.get_item_data(selected_item)

        # --- Check if field_value is a dictionary representing an entity ---
        # Intermediate nodes (like status or asset type) will have field_value as a string.
        # Leaf nodes or entity-linked intermediate nodes will have a dictionary.
        # The 'My Tasks' tab specifically puts the Task entity data here.
        entity_data_to_process = None
        if isinstance(field_value, dict) and 'type' in field_value and 'id' in field_value:
            # This looks like a ShotGrid entity dictionary (e.g., {'type': 'Asset', 'id': 123})
            # Or it could be the Task entity from the 'My Tasks' tab
            entity_data_to_process = field_value
            logger.debug(f"Using field_value as entity data: {entity_data_to_process}")
        elif isinstance(sg_data, dict) and 'type' in sg_data and 'id' in sg_data:
            # Fallback: If field_value wasn't an entity dict, check if sg_data is.
            # This might happen for leaf nodes where field_value is just the name.
            entity_data_to_process = sg_data
            logger.debug(f"Using sg_data as entity data: {entity_data_to_process}")
        else:
            logger.warning(
                f"Selected item does not represent a direct entity. sg_data: {sg_data}, field_value: {field_value}")
            self._add_log(
                "\n <span style='color:#FFD700'>Selected item is not a direct entity (e.g., Asset, Shot, Task). Cannot determine path.</span> \n",
                2)
            return None, None, None

        # --- Get the path using the identified entity data ---
        if not entity_data_to_process:
            logger.warning("Could not identify valid entity data for the selected item.")
            self._add_log(
                "\n <span style='color:#FFD700'>Could not get valid entity data for the selected item.</span> \n", 2)
            return None, None, None

        # Get the local filesystem path for the entity
        # Using _get_entity_info as it handles Tasks correctly
        entity_path, entity_id, entity_type = self._get_entity_info(entity_data_to_process)
        if not entity_path:
            logger.warning(
                f"Could not determine the filesystem path for the selected entity: {entity_data_to_process.get('type', 'N/A')} {entity_data_to_process.get('id', 'N/A')}")
            self._add_log(
                f"\n <span style='color:#FFD700'>Could not find the filesystem path for the selected {entity_data_to_process.get('type', 'N/A')}.</span> \n",
                2)
            return None, None, None

        logger.info(f"Selected entity path: {entity_path}, ID: {entity_id}, Type: {entity_type}")
        return entity_path, entity_id, entity_type
    def _get_selected_entity_path_info_old(self):
        """
        Finds the currently selected entity in the active preset tab,
        determines its filesystem path, and returns relevant info.

        :returns: Tuple (entity_path, entity_id, entity_type) or (None, None, None) if not found.
        """
        logger.debug("Getting path info for selected entity...")

        selected_item = self._get_selected_entity()
        if not selected_item:
            logger.warning("No entity selected in the tree view.")
            self._add_log(
                "\n <span style='color:#FFD700'>No entity selected. Please select an item in the left panel.</span> \n",
                2)
            return None, None, None

        # Extract the entity data from the selected item
        sg_data, entity_data = model_item_data.get_item_data(selected_item)
        if not entity_data:
            logger.warning("Could not retrieve entity data for the selected item.")
            self._add_log(
                "\n <span style='color:#FFD700'>Could not get data for the selected item.</span> \n", 2)
            return None, None, None

        if isinstance(entity_data, dict):
            # Use full entity info if available (e.g., for 'My Tasks' tab)
            entity_path, entity_id, entity_type = self._get_entity_info(entity_data)
        else:
            logger.warning("Entity data is not a dictionary. Falling back to basic sync resolution.")
            self._add_log(
                "\n <span style='color:#FFD700'>Warning: Entity data format unexpected. Attempting fallback method.</span> \n",
                2)
            # Fall back to simple method (more compatible with other tabs)
            entity_path, entity_id, entity_type = self._get_entity_for_sync(sg_data)

        if not entity_path:
            logger.warning(
                f"Could not determine the filesystem path for the selected entity: {entity_type} {entity_id}")
            self._add_log(
                f"\n <span style='color:#FFD700'>Could not find the filesystem path for the selected {entity_type or 'entity'}.</span> \n",
                2)
            return None, None, None

        logger.info(f"Selected entity path: {entity_path}, ID: {entity_id}, Type: {entity_type}")
        return entity_path, entity_id, entity_type


    def _get_selected_entity_path_info_original(self):
        """
        Finds the currently selected entity in the active preset tab,
        determines its filesystem path, and returns relevant info.

        :returns: Tuple (entity_path, entity_id, entity_type) or (None, None, None) if not found.
        """
        logger.debug("Getting path info for selected entity...")

        selected_item = self._get_selected_entity()
        if not selected_item:
            logger.warning("No entity selected in the tree view.")
            self._add_log(
                "\n <span style='color:#FFD700'>No entity selected. Please select an item in the left panel.</span> \n",
                2)
            return None, None, None

        # Extract the entity data from the selected item
        (sg_data, entity_data) = model_item_data.get_item_data(selected_item)
        if not entity_data:
            logger.warning("Could not retrieve entity data for the selected item.")
            self._add_log("\n <span style='color:#FFD700'>Could not get data for the selected item.</span> \n", 2)
            return None, None, None

        # Get the local filesystem path for the entity
        # Using _get_entity_info as it handles Tasks correctly
        entity_path, entity_id, entity_type = self._get_entity_info(entity_data)
        if not entity_path:
            logger.warning(
                f"Could not determine the filesystem path for the selected entity: {entity_data.get('type', 'N/A')} {entity_data.get('id', 'N/A')}")
            self._add_log(
                f"\n <span style='color:#FFD700'>Could not find the filesystem path for the selected {entity_data.get('type', 'N/A')}.</span> \n",
                2)
            return None, None, None

        logger.info(f"Selected entity path: {entity_path}, ID: {entity_id}, Type: {entity_type}")
        return entity_path, entity_id, entity_type

    def _get_preset_entity_path(self):
        """
        Refreshes the data displayed in the entity preset tabs, specifically
        updating the 'To Sync' count for the 'My Tasks' preset.
        """
        logger.debug("Refreshing entity preset tabs...")
        for preset_name, preset in self._entity_presets.items():
            if preset_name == "My Tasks":
                logger.debug("Refreshing 'My Tasks' preset tab.")
                view = preset.view
                proxy_model = preset.proxy_model
                source_model = proxy_model.sourceModel()

                # Ensure the model has the correct number of columns if it was somehow reset
                if source_model.columnCount() < 2:
                    source_model.setColumnCount(2)
                    source_model.setHorizontalHeaderLabels(["Name", "To Sync"])

                row_count = source_model.rowCount()
                logger.debug(f"Found {row_count} rows in 'My Tasks' model.")

                for row in range(row_count):
                    proxy_index = proxy_model.index(row, 0)
                    if not proxy_index.isValid():
                        # logger.debug(f"[REFRESH] Row {row}: Invalid proxy index")
                        continue

                    source_index = proxy_model.mapToSource(proxy_index)
                    if not source_index.isValid():
                        # logger.debug(f"[REFRESH] Row {row}: Invalid source index")
                        continue

                    # Get item using source_index.model()
                    item_model = source_index.model()
                    item = item_model.itemFromIndex(source_index)

                    if not item:
                        # logger.debug(f"[REFRESH] Row {row}: No item in model")
                        continue

                    # Extract the Shotgun data and field value from the node item.
                    (sg_data, entity_data) = model_item_data.get_item_data(item)

                    entity_path, entity_id, entity_type = self._get_entity_info(entity_data)
                    if not entity_id or not entity_type or not entity_path:
                        # logger.debug(
                        #    f"[REFRESH] Row {row}: Invalid entity info — Path: {entity_path}, ID: {entity_id}, Type: {entity_type}")
                        # Ensure the second column exists even if entity info is bad
                        if source_model.item(source_index.row(), 1) is None:
                            source_model.setItem(source_index.row(), 1, QStandardItem("N/A"))
                        continue

                    # logger.debug(f"[REFRESH] Row {row}: Entity Path: {entity_path}")
                    sync_count = self._get_sync_count_for_entity(entity_path)
                    # logger.debug(f"[REFRESH] Row {row}: Sync count = {sync_count}")

                    # Set value into the second column
                    if sync_count == 0:
                        msg = "Up to date"
                    else:
                        msg = "{} To Sync".format(sync_count)

                    # Get or create the item for the second column
                    desc_item = source_model.item(source_index.row(), 1)
                    if desc_item is None:
                        desc_item = QStandardItem()
                        source_model.setItem(source_index.row(), 1, desc_item)

                    desc_item.setText(str(msg))  # Update text
                    sync_icon = self.sync_icons.get_sync_pixmap(sync_count)
                    if sync_icon:
                        desc_item.setIcon(sync_icon)  # Update icon
                    else:
                        desc_item.setIcon(QIcon())  # Clear icon if none

                logger.debug("Finished refreshing 'My Tasks' preset tab.")
                # Trigger layout change to ensure the view updates visually
                #source_model.layoutChanged.emit()
                # view.update()  # <--- Removed this line
                break  # Stop after refreshing 'My Tasks'

        logger.debug("Entity preset tabs refresh complete.")
    def _get_entity_for_sync(self, entity_data):
        """
        Get entity path, ID, and type from entity data. Handles cases where
        entity_data might not be a dictionary.
        """
        entity_path, entity_id, entity_type = None, 0, None
        logger.debug(">>>>>>>>>>>>>> _get_entity_for_sync received data: {} (Type: {})".format(entity_data, type(entity_data)))

        # Ensure entity_data is not None/empty and is a dictionary before proceeding
        if entity_data and isinstance(entity_data, dict):
            entity_id = entity_data.get('id', 0)
            entity_type = entity_data.get('type', None)

            # Special handling for Task entities to get the linked entity
            if entity_type == "Task":
                entity = entity_data.get("entity", None)
                if isinstance(entity, dict):  # Check if the linked entity is also a dict
                    entity_id = entity.get('id', 0)
                    entity_type = entity.get('type', None)
                else:
                    # If the linked entity isn't a dict, reset id/type
                    entity_id = 0
                    entity_type = None
                    logger.warning(f"Task's linked entity is not a dictionary: {entity}")

            # Only try to get the path if we have a valid type and ID
            if entity_type and entity_id:
                try:
                    paths = self._app.sgtk.paths_from_entity(entity_type, entity_id)
                    if paths and len(paths) > 0:
                        entity_path = paths[-1]
                        logger.debug(f"Found entity path: {entity_path}")
                    else:
                        logger.warning(f"Could not determine path for {entity_type} ID {entity_id}")
                except Exception as e:
                    logger.error(f"Error getting path for {entity_type} ID {entity_id}: {e}")
            else:
                # Log if we couldn't extract a valid type/id from the dictionary
                logger.debug(f"Could not extract valid entity type/id from entity_data: {entity_data}")

        elif entity_data:
            # Log a warning if entity_data was provided but wasn't a dictionary
            logger.warning(f"_get_entity_info received non-dictionary data: {entity_data} (Type: {type(entity_data)})")

        return entity_path, entity_id, entity_type

    def _create_pending_view_context_menu(self):

        self._pending_view_publish_action = QAction("Publish...", self._pending_view_widget)
        self._pending_view_publish_action.triggered.connect(lambda: self._on_pending_view_model_action("publish"))
        self._pending_view_revert_action = QAction("Revert", self._pending_view_widget)
        self._pending_view_revert_action.triggered.connect(lambda: self._on_pending_view_model_action("revert"))
        self._pending_view_move_action = QAction("Move to Changelist", self._pending_view_widget)
        self._pending_view_move_action.triggered.connect(lambda: self._on_pending_view_model_action("move"))


        self._pending_view_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self._pending_view_widget.customContextMenuRequested.connect(
            self._show_pending_view_actions
        )

    def _show_pending_view_actions(self, pos):
        """
               Shows the actions for the current pending view selection.

               :param pos: Local coordinates inside the viewport when the context menu was requested.
        """

        # Get the index of the item at the menu position
        index = self._pending_view_widget.indexAt(pos)
        if not index.isValid():
            return

        # Determine if the index is a parent or a child
        is_parent = not index.parent().isValid()

        # Set selection mode based on whether the item is a parent or a child
        #if is_parent:
        #    self._pending_view_widget.single_selection()
        # else:
        #    self._pending_view_widget.multi_selection()

        # Build a menu with all the actions.
        menu = QMenu(self)

        # Add "Publish..." for parent rows, "Revert" for child rows
        if is_parent:
            menu.addAction(self._pending_view_publish_action)
        else:
            menu.addAction(self._pending_view_revert_action)
            menu.addSeparator()
            menu.addAction(self._pending_view_move_action)

        menu.addSeparator()

        # Calculate the global position of the menu
        global_pos = self._pending_view_widget.mapToGlobal(pos)

        # Execute the menu using a QEventLoop to block until an action is triggered
        event_loop = QEventLoop()
        menu.aboutToHide.connect(event_loop.quit)
        menu.exec_(global_pos)
        event_loop.exec_()

    def _list_files_in_changelist(self, change):
        try:
            p4_result = self._p4.run("describe", "-s", str(change))
            logger.debug("p4_result for {change}: {p4_result}")
            files_in_changelist = []
            for depot_file in p4_result[0]["depotFile"]:
                client_file = self._get_client_file(depot_file)
                files_in_changelist.append(client_file)
            return files_in_changelist
        except Exception as e:
            logger.debug("Error listing files in changelist {}: {}".format(change, e))
            return []

    def _validate_changelist_files(self, files_in_changelist):
        """ Validate changelist files """
        error_list = []
        for filepath in files_in_changelist:
            sg_item = {}
            sg_item["path"] = {}
            sg_item["path"]["local_path"] = filepath
            entity, published_file = self.get_entity_from_sg_item(sg_item)
            #logger.debug("_validate_changelist_files: entity: {}".format(entity))
            #logger.debug("_validate_changelist_files: published_file: {}".format(published_file))
            if not entity:
                error_list.append(filepath)
                logger.debug("_validate_changelist_files: error_list: {}".format(error_list))
        if error_list and len(error_list)>0:
            return False, error_list
        else:
            return True, error_list

    def _on_pending_view_model_action(self, action):
        selected_files_to_revert = []
        selected_files_to_delete = []
        selected_actions_to_move = []
        selected_files_to_move = []
        engine = sgtk.platform.current_engine()
        # logger.debug(">>>>>>>>>>> engine is: {}".format(engine))

        # First, gather all the files that are to be reverted
        selected_indexes = self._pending_view_widget.selectionModel().selectedRows()
        change = 0
        files_in_changelist = []
        description = ""
        if action == "publish" and selected_indexes:
            for selected_index in selected_indexes:
                try:
                    source_index = self._pending_view_model.mapToSource(selected_index)
                    change, description = self._get_pending_info_from_source(source_index)
                except Exception as e:
                    logger.debug("Error processing selection: {}".format(e))
            if change:
                files_in_changelist = self._list_files_in_changelist(change)
                logger.debug("Files in changelist {}: {}".format(change, files_in_changelist))
                # Validate changelist files using threading
                result, error_list = self._validate_changelist_files_with_threads(files_in_changelist)

                if not result:
                        msg = "\n <span style='color:#CC3333'>The following files in the changelist {} are not linked to any Shotgrid entity:</span> \n".format(change)
                        self._add_log(msg, 2)
                        for filepath in error_list:
                            msg = "\n <span style='color:#CC3333'>{}</span> \n".format(filepath)
                            self._add_log(msg, 2)
                        # Exit without publishing
                        return

            try:
                try:
                    # Create the description file
                    self._create_description_file(files_in_changelist, description)
                except:
                    pass
                logger.debug("change is: {}".format(change))
                """
                engine = sgtk.platform.current_engine()
                if engine:
                    logger.debug("Running the publish command...")
                    logger.debug("Current engine: {}".format(engine))

                    # Get all available commands in the engine
                    logger.debug("Available commands: {}".format(engine.commands.keys()))

                    app_command = engine.commands.get("Publish...")

                    if app_command:
                        logger.debug("Found 'Publish...' command.")
                        logger.debug("Command details: {}".format(app_command))

                        # Log the callback function before calling it
                        callback_func = app_command.get("callback")
                        logger.debug("Callback function: {}".format(callback_func))

                        if callback_func:
                            logger.debug(">>>>> Pass in the desired changelist parameter: {}".format(change))
                            callback_func(change)
                        else:
                            logger.warning("No callback function found in 'Publish...' command.")
                    else:
                        logger.warning("'Publish...' command not found in engine.commands.")
                """
                engine = sgtk.platform.current_engine()
                if engine:
                    logger.debug("Running the publish command...")
                    app_command = engine.commands.get("Publish...")
                    # logger.debug("Completed running the publish command")

                    if app_command:
                        # now run the command, which in this case will launch the Publish app,
                        # passing in the desired changelist parameter.
                        # app_command["callback"](change)
                        logger.debug(">>>>> Pass in the desired changelist parameter: {}".format(change))
                        app_command["callback"](change)

                        # Start the after_publish_ui_close method in a new thread
                        # threading.Thread(target=self._after_publish_ui_close).start()

                        # After the UI closes, call _populate_pending_widget
                        # wait_thread = threading.Thread(target=self._after_publish_ui_close)
                        # wait_thread.start()

                        # Start a new thread to wait for the UI to close
                        #wait_thread = threading.Thread(target=self._wait_for_ui_close)
                        #wait_thread.start()

                        #wait_thread = UIWaitThread(self._check_ui_closed, self)
                        # wait_thread.start()



            except Exception as e:
                logger.debug("Error loading publisher: {}".format(e))


        # If the action is revert, then proceed
        if action == "revert" and selected_indexes:
            for selected_index in selected_indexes:
                try:
                    source_index = self._pending_view_model.mapToSource(selected_index)
                    selected_row_data = self._get_pending_data_from_source(source_index)
                    action = self._get_action_data_from_source(source_index)
                    change = self._get_change_data_from_source(source_index)
                    if selected_row_data and "#" in selected_row_data:
                        target_file = selected_row_data.split("#")[0]
                        target_file = target_file.strip()
                        selected_files_to_revert.append(target_file)
                        if action in ["add"]:
                            selected_files_to_delete.append((change,target_file))

                except Exception as e:
                    logger.debug("Error processing selection: {}".format(e))
            if selected_files_to_revert:
                # Convert list of files into a string, to show in the confirmation dialog
                files_str = "\n".join(selected_files_to_revert)

                # Show confirmation dialog
                reply = QMessageBox.question(self, 'Confirmation',
                                             f"Are you sure you want to revert the following files?\n\n{files_str}",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

                if reply == QMessageBox.Yes:
                    for target_file in selected_files_to_revert:
                        try:
                            msg = f"Reverting file {target_file} ..."
                            self._add_log(msg, 3)
                            p4_result = self._p4.run("revert", target_file)
                            logger.debug("p4_result for {target_file}: {p4_result}")
                        except Exception as e:
                            logger.debug("Unable to revert file: {}, Error: {}".format(target_file, e))
            if selected_files_to_delete:
                # Convert list of files into a string, to show in the confirmation dialog
                files_str = "\n".join(selected_files_to_revert)

                # Show confirmation dialog
                reply = QMessageBox.question(self, 'Confirmation',
                                             f"Are you sure you want to delete the following files?\n\n{files_str}",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

                if reply == QMessageBox.Yes:
                    self._delete_pending_data(selected_files_to_revert)
                    """
                    for change, target_file in selected_files_to_revert:
                        try:
                            msg = f"Deleting file {target_file} ..."
                            self._add_log(msg, 3)
                            self._delete_pending_file(target_file)
                        except Exception as e:
                            logger.debug("Unable to delete file: {}, Error: {}".format(target_file, e))
                    """
        # If the action is move, then move files to a different changelist
        if action == "move" and selected_indexes:
            logger.debug("Move files to a different changelist")
            for selected_index in selected_indexes:
                try:
                    source_index = self._pending_view_model.mapToSource(selected_index)
                    selected_row_data = self._get_pending_data_from_source(source_index)
                    change = self._get_change_data_from_source(source_index)
                    if selected_row_data:
                        # get the sg_tem from the source index
                        action = self._get_action_data_from_source(source_index)
                        sg_item = self._get_sg_data_from_source(source_index)
                        selected_actions_to_move.append((sg_item, action))
                        target_file = sg_item.get("depotFile", None)
                        # If there is no depot file, try to get the local path
                        if not target_file:
                            if "path" in sg_item:
                                if "local_path" in sg_item["path"]:
                                    target_file = sg_item["path"].get("local_path", None)
                        if target_file:
                            selected_files_to_move.append(target_file)

                except Exception as e:
                    logger.debug("Error processing selection: {}".format(e))
            if selected_files_to_move:
                # Convert list of files into a string, to show in the confirmation dialog
                files_str = "\n".join(selected_files_to_move)

                # Show confirmation dialog
                reply = QMessageBox.question(self, 'Confirmation',
                                                   f"Do you wish to transfer the selected files to a new changelist?\n\n{files_str}",
                                                   QMessageBox.Yes | QMessageBox.No,
                                                   QMessageBox.No)

                if reply == QMessageBox.Yes:
                        try:
                            if selected_actions_to_move:
                                self.perform_changelist_selection(selected_actions_to_move)
                        except Exception as e:
                            logger.debug("Unable to revert file: {}, Error: {}".format(target_file, e))

        if selected_files_to_revert or selected_files_to_delete or selected_files_to_move:
            self._populate_pending_widget()

    import threading
    import os

    def _validate_changelist_files_with_threads(self, files_in_changelist):
        """
        Validate changelist files using threading for faster execution, adapting to the machine's capabilities.
        """
        # Use the number of available CPU cores for thread count or default to 1 if detection fails
        num_threads = max(1, os.cpu_count() or 1)
        files_per_thread = len(files_in_changelist) // num_threads
        error_list = []
        results = []

        def validate_files_sublist(files_sublist):
            """
            Thread-safe validation of a sublist of files.
            """
            result, errors = self._validate_changelist_files(files_sublist)
            results.append(result)
            error_list.extend(errors)

        threads = []
        for i in range(num_threads):
            start_index = i * files_per_thread
            end_index = start_index + files_per_thread
            if i == num_threads - 1:  # Ensure the last thread handles remaining files
                end_index = len(files_in_changelist)
            files_sublist = files_in_changelist[start_index:end_index]

            # Create and start a thread for the sublist
            thread = threading.Thread(target=validate_files_sublist, args=(files_sublist,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Consolidate results
        overall_result = all(results)
        return overall_result, error_list

    def _after_publish_ui_close(self):
        logger.debug("Checking if the publisher UI is closed...")
        # Setup a QTimer to periodically check the condition
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_publisher_ui_closed)
        self.timer.start(1000)  # Check every 1000 milliseconds (1 second)

    def check_publisher_ui_closed(self):
        logger.debug("Checking if the publisher UI is closed through the timer...")
        if os.path.exists(self._publisher_is_closed_path):
            logger.debug("Reading publisher is closed status file {}...".format(self._publisher_is_closed_path))
            with open(self._publisher_is_closed_path, 'r') as infile:
                first_line = infile.readline().strip()

            if "GUI_IS_CLOSED" in first_line:
                self._populate_pending_widget()

            os.remove(self._publisher_is_closed_path)
            self.timer.stop()  # Stop the timer once the file is found and processed

    def _wait_for_ui_close(self):
        # Placeholder for logic to check if the UI window is closed
        ui_is_open = True  # You will need to implement this check based on your UI framework
        while ui_is_open:
            time.sleep(1)  # Check every second (adjust the timing as necessary)
            # Update the condition to check if the UI window is still open
            ui_is_open = self._check_ui_closed()  # Implement this method based on your UI

        msg = "\n <span style='color:#2C93E2'>Updating the Pending View ...</span> \n"
        self._add_log(msg, 2)
        self.update_pending_view()



    def _check_ui_closed(self):
        """
        Display publisher UI is closed status
        """
        try:
            logger.debug(
                "checking for publisher is_closed status file: {} ...".format(self._publisher_is_closed_path))

            if not os.path.exists(self._publisher_is_closed_path):
                logger.debug("publisher is_closed file does not exist")
                return None

            with open(self._publisher_is_closed_path, 'r') as in_file:
                for line in in_file:
                    line = line.rstrip()
                    # logger.debug(">>>> line: {}".format(line))
                    if ":::" in line:
                        parts = line.split(":::")
                        if len(parts) == 2:
                            base_file, status = parts
                            logger.debug("publisher UI is closed status is: {}".format(status))
                            msg = "\n <span style='color:#2C93E2'>Updating the Pending View ...</span> \n"
                            self._add_log(msg, 2)
                            self.update_pending_view()
                            return status == 'True'
                        else:
                            # This handles the case where the split does not result in 2 parts
                            logger.debug("Error: Line does not conform to expected format: '{}'".format(line))
                            return False
                    else:
                        # Handle lines without delimiter or skip
                        # For example, you might want to log a warning or error
                        #logger.debug("Line without delimiter: {}".format(line))
                        return False
        except Exception as e:
            logger.debug("Error reading publisher is closed file status {}".format(e))
            return False

    def _create_description_file(self, files_in_changelist, description):
        try:
            if files_in_changelist:
                with open(self._publish_files_description, "w") as f:
                    for file in files_in_changelist:
                        base_file = os.path.basename(file)
                        msg = f"{base_file}:::{description}"
                        f.write(msg)
                        f.write("\n")

        except Exception as e:
            logger.debug("Error creating description file: {}".format(e))

    def _delete_pending_file(self, change, target_file):
        try:
            # Mark the file for delete in Perforce
            p4_result = self._p4.run("delete", target_file)
            # Submit the file to Perforce
            submit_del_res = submit_change(self._p4, change, target_file)
            logger.debug("p4_result for {target_file}: {submit_del_res}")
        except Exception as e:
            logger.debug("Unable to delete file: {}, Error: {}".format(target_file, e))

    def _get_pending_data_from_source(self, source_index):
        # Get data from the source model using the source index
        if source_index.isValid():
            parent_item = source_index.model().itemFromIndex(source_index.parent())

            # If the parent item exists, fetch the child item.
            # Otherwise, just fetch the item at the top level (as you did before)
            if parent_item:
                child_item = parent_item.child(source_index.row(), 0)
            else:
                child_item = source_index.model().item(source_index.row(), 0)

            if child_item:
                return child_item.text()
        return None

    def _get_action_data_from_source(self, source_index):
        # Get data from the source model using the source index
        if source_index.isValid():
            id_role = QtCore.Qt.UserRole + 1
            action = source_index.data(id_role)
            return action
        return None

    def _get_change_data_from_source(self, source_index):
        # Get data from the source model using the source index
        if source_index.isValid():
            id_role = QtCore.Qt.UserRole + 2
            change = source_index.data(id_role)
            if change and change != "default":
                change = int(change)
                return change
            if change == "default":
                return change

        return 0


    def _get_sg_data_from_source(self, source_index):
        # Get sg_item from the source model using the source index
        try:
            if source_index.isValid():
                id_role = QtCore.Qt.UserRole + 3
                sg_item = source_index.data(id_role)
                if sg_item:
                    return sg_item
        except Exception as e:
            logger.debug("Unable to get sg_item data: {}".format(e))
        return None

    def _get_pending_info_from_source(self, source_index):
        # Get changelist from the source model using the source index
        if source_index.isValid():
            item_model = source_index.model()
            parent_index = source_index.parent()

            # If the parent index is valid, it means the item is a child.
            # In that case, get the parent item and its data.
            # Otherwise, it means the item is a parent, so get its data directly.
            if parent_index.isValid():
                parent_item = item_model.itemFromIndex(parent_index)
                changelist = parent_item.data(QtCore.Qt.UserRole)
                description = parent_item.data(QtCore.Qt.UserRole + 4)
            else:
                item = item_model.itemFromIndex(source_index)
                changelist = item.data(QtCore.Qt.UserRole)
                description = item.data(QtCore.Qt.UserRole + 4)

            return changelist, description
        return None

    def _populate_column_view_widget(self):
        #self._publish_model.hard_refresh()
        self._column_view_dict = {}
        self._standard_item_dict = {}
        
        logger.debug("Setting up Column View table ...")
        self._setup_column_view()
        logger.debug("Getting Perforce data...")
        self._perforce_sg_data = self._get_perforce_sg_data()
        length = len(self._perforce_sg_data)
        if not self._perforce_sg_data:
            self._perforce_sg_data = self._sg_data
        if self._perforce_sg_data and length > 0:
            msg = "\n <span style='color:#2C93E2'>Populating the Column View with {} files. Please wait...</span> \n".format(
                length)
            self._add_log(msg, 2)
            logger.debug("Getting Perforce file size...")
            self._perforce_sg_data = self._get_perforce_size(self._perforce_sg_data)
            logger.debug("Populating Column View table...")

            logger.debug("Updating Column View is complete")
            for sg_item in self._perforce_sg_data:
                # logger.debug("------------------------------------------")
                #for k, v in sg_item.items():
                #   logger.debug(">>> {}:{}".format(k, v))
                id = sg_item.get("id", 0)
                new_sg_item, sg_list = self._get_column_data(sg_item)
                #logger.debug(">>> original sg_item: {}".format(sg_item))
                #logger.debug(">>> new sg_item: {}".format(new_sg_item))
                if id not in self._column_view_dict and new_sg_item:
                    self._column_view_dict[id] = new_sg_item
                #logger.debug(">>> sg_list: {}".format(sg_list))
                if sg_list:

                    #item = [QStandardItem(str(data)) for data in sg_list]
                    self._standard_item_dict[id] = sg_list
            #logger.debug(">>> self._column_view_dict: {}".format(self._column_view_dict))
            #logger.debug(">>> self._standard_item_dict: {}".format(self._standard_item_dict))
            #self._populate_column_view_no_groups()
            self._get_grouped_column_view_data()
            self._get_publish_icons()
            self._set_column_group()

    def _set_column_group(self):
        if self._current_column_view_grouping == self.COLUMN_VIEW_UNGROUP:
            self._no_groups()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_FOLDER:
            self._group_by_folder()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_ACTION:
            self._group_by_action()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_REVISION:
            self._group_by_revision()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_EXTENSION:
            self._group_by_file_extension()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_TYPE:
            self._group_by_type()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_USER:
            self._group_by_user()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_TASK:
            self._group_by_task_name()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_STATUS:
            self._group_by_task_status()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_STEP:
            self._group_by_step()
        elif self._current_column_view_grouping == self.COLUMN_VIEW_GROUP_BY_DATE_MODIFIED:
            self._group_by_date_modified()
        else:
            raise ValueError("Invalid column view grouping specified!")

    def _get_grouped_column_view_data(self):

        self._folder_dict = self._get_column_dict("folder")
        #logger.debug(">>> self._folder_dict: {}".format(self._folder_dict))
        self._action_dict = self._get_column_dict("action")
        self._revision_dict = self._get_column_dict("revision")
        self._file_extension_dict = self._get_column_dict("file_extension")
        self._type_dict = self._get_column_dict("file_type")
        self._task_name_dict = self._get_column_dict("task_name")
        self._task_status_dict = self._get_column_dict("task_status")
        self._user_dict = self._get_column_dict("user")
        self._step_dict = self._get_column_dict("step")
        self._date_modified_dict = self._get_column_dict("date_modified")

    def _get_column_dict(self, key):
        column_dict = {}
        for id, sg_item in self._column_view_dict.items():
            if sg_item:
                value = sg_item.get(key)
                # logger.debug(">>> value: {}".format(value))
                # logger.debug(">>> id: {}".format(id))
                if value is not None and key != "folder":
                    column_dict.setdefault(value, []).append(self._standard_item_dict.get(id))
                else:
                    column_dict.setdefault(value or "N/A", []).append(self._standard_item_dict.get(id))

        return column_dict

    def _get_column_data(self, sg_item):
        new_sg_item = sg_item
        sg_list = []
        if not sg_item:
            return new_sg_item, sg_list

        # logger.debug(">>> In _get_column_data, getting column data for sg_item: {}".format(sg_item))
        #try:
        # logger.debug(">>> Getting row {} data".format(row))
        # self._print_sg_item(sg_item)
        # Extract relevant data from the Shotgun response
        name = sg_item.get("name", "N/A")
        new_sg_item["name"] = name
        action = sg_item.get("action") or sg_item.get("headAction") or "N/A"
        new_sg_item["action"] = action
        revision = sg_item.get("revision", "N/A")
        if revision != "N/A":
            #revision = "#{}".format(revision)
            new_sg_item["revision"] = revision

        local_path = "N/A"
        folder = "N/A"
        # logger.debug(">>> Getting path data")
        if "path" in sg_item:
            path = sg_item.get("path", None)
            # logger.debug(">>> path: {}".format(path))
            if path:
                local_path = path.get("local_path", "N/A")
                if local_path and local_path != "N/A":
                    local_directory = os.path.dirname(local_path)
                    entity_path = self._entity_path
                    if local_directory and not entity_path:
                        entity = sg_item.get("entity", None)
                        if entity:
                            # Get entity path
                            entity_path = self._get_entity_path(entity)

                    if entity_path and local_directory:
                        logger.debug("entity_path: {}".format(entity_path))
                        logger.debug("local_directory: {}".format(local_directory))
                        folder = self._path_difference(entity_path, local_directory)

                    if local_directory and not entity_path:
                        # Get the parent directory of local_directory
                        folder = os.path.basename(local_directory)
                        logger.debug("No entity path found, we will use parent folder: {}".format(folder))
                    if folder and folder != "N/A":
                        # folder = "{}\\".format(difference_str)
                        new_sg_item["folder"] = folder

        file_extension = "N/A"
        if local_path and local_path != "N/A":
            file_extension = local_path.split(".")[-1] or "N/A"
            new_sg_item["file_extension"] = file_extension

        type = "N/A"
        if file_extension and file_extension != "N/A":
            type = self.settings.get(file_extension, "N/A")
            new_sg_item["file_type"] = type

        size = sg_item.get("fileSize", 0)
        new_sg_item["size"] = size

        # published_file_type = sg_item.get("published_file_type", {}).get("name", "N/A")

        description = sg_item.get("description", "N/A")
        #new_sg_item["description"] = description
        if description:
            description = description.split("\n")[0]

        publish_id = 0
        if "id" in sg_item:
            publish_id = sg_item.get("id", 0)
            new_sg_item["publish_id"] = publish_id

        task_name = "N/A"
        step = "N/A"
        if "task" in sg_item:
            task = sg_item.get("task", None)
            if task:
                task_name = task.get("name", "N/A")
                new_sg_item["task_name"] = task_name

                step = sg_item.get("task.Task.step.Step.code", None)
                # logger.debug(">>> step: {}".format(step))
                if not step:
                    step = self._get_pipeline_step(publish_id)
                new_sg_item["step"] = step
                # step = sg_item.get("step", {}).get("name", "N/A")
                # step = sg_item.get("task.Task.step.Step.code", "N/A") if step == "N/A" else step

        task_status = sg_item.get("task.Task.sg_status_list", "N/A")
        new_sg_item["task_status"] = task_status

        user = "N/A"
        if "created_by" in sg_item:
            user = sg_item.get("created_by", None)
            if user:
                user = user.get("name", "N/A")
                new_sg_item["user"] = user

        dt = sg_item.get("created_at") or sg_item.get("headModTime") or sg_item.get("headTime") or None
        # logger.debug(">>> dt: {}".format(dt))
        dt = float(dt) if dt else 0
        date = self._get_publish_time_for_column_view(dt)
        new_sg_item["date"] = date
        # logger.debug(">>> date: {}".format(date))
        date_modified = self._get_modified_date(dt)
        new_sg_item["date_modified"] = date_modified
        # logger.debug(">>> date_modified: {}".format(date_modified))

        # Create a list of QStandardItems for each column
        sg_list = ["", folder, action, name, revision, size, file_extension, type, user, task_name, task_status, step, date,date_modified,
                   publish_id,
                   description]
                
        #except Exception as e:
        #    logger.debug(">>> Error getting column data for sg_item, error {}".format(e))
        return new_sg_item, sg_list

    def _get_pipeline_step(self, published_file_id):

        pipeline_step = "N/A"
        published_file = self._app.shotgun.find_one("PublishedFile", [["id", "is", published_file_id]], ["id", "code", "pipeline_step", "task.Task.step.Step.code", "step"])
        if published_file:
            # logger.debug(">>>>>>>>> published_file: {}".format(published_file))
            pipeline_step = published_file.get("task.Task.step.Step.code", "N/A")
            # logger.debug(">>>>>>>>> pipeline_step: {}".format(pipeline_step))
            """
            if not pipeline_step:
                task = published_file.get("task")
                if task:
                    pipeline_step = task.get("step")
            """
        return pipeline_step

    def _get_modified_date(self, dt):

        publish_time = create_modified_date(dt)
        return publish_time

    def _get_publish_time_for_column_view(self, dt):
        publish_time = "N/A"
        if dt > 0:
            publish_time = datetime.datetime.fromtimestamp(dt).strftime(
                "%Y-%m-%d %H:%M"
            )

        return publish_time

    def _get_publish_time_for_column_view_old(self, sg_item):
        publish_time = "N/A"
        version_numer = int(sg_item.get("version_number", 0))
        if version_numer == 0:
            # No prior publish, use Perforce creation time as publish time
            dt = sg_item.get("headModTime") or self.sg_item.get("headTime") or None
            # logger.debug(">>>>> dt is: {}".format(dt))
            # if dt:
            #    publish_time = create_human_readable_timestamp(dt)
        else:

            dt = sg_item.get("created_at") or 0
            # publish_time = create_human_readable_timestamp(dt)
            """
            if dt > 0:
                publish_time = datetime.datetime.fromtimestamp(dt).strftime(
                    "%Y-%m-%d %H:%M"
                )
            else:
                publish_time = "N/A"
            """
        publish_time = dt
        # logger.debug(">>>>> Publish time is: {}".format(publish_time))
        return publish_time

    def _get_entity_path(self, entity_data):
        """
        Get entity path
        """
        if not entity_data:
            return None

        entity_id = entity_data.get('id', 0)
        entity_type = entity_data.get('type', None)
        # entity_name = entity_data.get('name', None)
        if entity_type == "Task":
            entity = entity_data.get("entity", None)
            if entity:
                entity_id = entity.get('id', entity_id)
                entity_type = entity.get('type', entity_type)

        entity_path = self._app.sgtk.paths_from_entity(entity_type, entity_id)
        #if not entity_path:
        #    # Fetch the entity using the id and type
        #    target_entity = self._app.shotgun.find_one(entity_type, [['id', 'is', entity_id]],
        #                         ['code', 'path', 'sg_status_list', 'description'])
        #    logger.debug(">>> target_entity: {}".format(target_entity))
        #    entity_path = target_entity.get("path", None)

        return entity_path[-1] if entity_path else None

    def _get_perforce_sg_data(self):
        perforce_sg_data = []

        model = self.ui.publish_view.model()
        if model.rowCount() > 0:
            for row in range(model.rowCount()):
                model_index = model.index(row, 0)
                proxy_model = model_index.model()
                source_index = proxy_model.mapToSource(model_index)
                item = source_index.model().itemFromIndex(source_index)

                is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
                if not is_folder:
                    # Run default action.
                    sg_item = shotgun_model.get_sg_data(model_index)
                    if sg_item:
                        perforce_sg_data.append(sg_item)
        return perforce_sg_data

    def _clean_sg_data(self):
        try:
            is_model_changed = False
            model = self.ui.publish_view.model()
            if model.rowCount() > 0:
                for row in range(model.rowCount()):
                    model_index = model.index(row, 0)
                    proxy_model = model_index.model()
                    source_index = proxy_model.mapToSource(model_index)
                    item = source_index.model().itemFromIndex(source_index)

                    is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
                    if not is_folder:
                        # Run default action.
                        sg_item = shotgun_model.get_sg_data(model_index)
                        action = sg_item.get("action") or sg_item.get("headAction") or None
                        if action and action in ["delete"]:
                            # remove the item from the model
                            model.removeRow(row)
                            is_model_changed = True

                if is_model_changed:
                    # Refresh the model
                    model.layoutChanged.emit()
                    # Refresh the view
                    self.ui.publish_view.update()
        except:
            pass




    def _reset_perforce_widget(self):
        self.ui.column_view = QTableView()
    
    def _setup_column_view(self):

        # Create a table model and set headers
        self.column_view_model = QStandardItemModel(0, len(self._headers))
        self.column_view_model.setHorizontalHeaderLabels(self._headers)

        # Create a proxy model for sorting and grouping
        self.perforce_proxy_model = QtGui.QSortFilterProxyModel()
        self.perforce_proxy_model.setSourceModel(self.column_view_model)

        self.ui.column_view.setModel(self.perforce_proxy_model)

        header = self.ui.column_view.header()
        for col in range(len(self._headers)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        self.ui.column_view.clicked.connect(self.on_column_view_row_clicked)

        self._create_column_view_context_menu()
        # Create the context menu for the header
        self._create_column_view_header_context_menu()


    def _create_column_view_header_context_menu(self):
        header = self.ui.column_view.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_column_header_context_menu)

    def _show_column_header_context_menu(self, pos):
        header = self.ui.column_view.header()
        col_idx = header.logicalIndexAt(pos)
        col_name = self.column_view_model.horizontalHeaderItem(col_idx).text()

        menu = QMenu(self.ui.column_view)

        # Add the "Group by folder" menu item
        self._group_by_folder_action = QAction("Group by folder", self.ui.column_view)
        self._group_by_folder_action.triggered.connect(self._group_by_folder)

        # Add the "Group by action" menu item
        self._group_by_action_action = QAction("Group by action", self.ui.column_view)
        self._group_by_action_action.triggered.connect(self._group_by_action)

        # Add grouping options for revision, file extension, type, task name, and task status
        self._group_by_revision_action = QAction("Group by Revision", self.ui.column_view)
        self._group_by_revision_action.triggered.connect(self._group_by_revision)

        self._group_by_file_extension_action = QAction("Group by File Extension", self.ui.column_view)
        self._group_by_file_extension_action.triggered.connect(self._group_by_file_extension)

        self._group_by_type_action = QAction("Group by Type", self.ui.column_view)
        self._group_by_type_action.triggered.connect(self._group_by_type)

        # Add the "Group by user" menu item
        self._group_by_user_action = QAction("Group by user", self.ui.column_view)
        self._group_by_user_action.triggered.connect(self._group_by_user)

        self._group_by_task_name_action = QAction("Group by Task Name", self.ui.column_view)
        self._group_by_task_name_action.triggered.connect(self._group_by_task_name)

        self._group_by_task_status_action = QAction("Group by Task Status", self.ui.column_view)
        self._group_by_task_status_action.triggered.connect(self._group_by_task_status)

        self._group_by_step_action = QAction("Group by Task Step", self.ui.column_view)
        self._group_by_step_action.triggered.connect(self._group_by_step)

        self._group_by_date_modified_action = QAction("Group by Date Modified", self.ui.column_view)
        self._group_by_date_modified_action.triggered.connect(self._group_by_date_modified)

        # Add a general Ungroup option
        self._no_groups_action = QAction("Ungroup", self.ui.column_view)
        self._no_groups_action.triggered.connect(self._no_groups)

        # Add "Expand All" action
        self._expand_all_action = QAction("Expand All", self.ui.column_view)
        self._expand_all_action.triggered.connect(self._expand_all)

        # Add "Collapse All" action
        self._collapse_all_action = QAction("Collapse All", self.ui.column_view)
        self._collapse_all_action.triggered.connect(self._collapse_all)

        # Map each column to its relevant action(s)
        actions_map = {
            "Folder": [self._group_by_folder_action],
            "Action": [self._group_by_action_action],
            "Revision#": [self._group_by_revision_action],
            "Extension": [self._group_by_file_extension_action],
            "Type": [self._group_by_type_action],
            "User": [self._group_by_user_action],  # Change "user" to "User"
            "Task": [self._group_by_task_name_action],
            "Status": [self._group_by_task_status_action],
            "Step": [self._group_by_step_action],
            "Date Modified": [self._group_by_date_modified_action],
        }

        # Add actions that are always present, regardless of the column
        common_actions = [self._expand_all_action, self._collapse_all_action]

        # Add actions

        # Add actions based on the current column
        for action in actions_map.get(col_name, []):
            menu.addAction(action)

        menu.addSeparator()

        menu.addAction(self._no_groups_action)
        menu.addSeparator()

        # Add common actions
        for action in common_actions:
            menu.addAction(action)

        # Calculate the global position of the menu
        global_pos = header.mapToGlobal(pos)

        # Execute the menu using a QEventLoop to block until an action is triggered
        event_loop = QEventLoop()
        menu.aboutToHide.connect(event_loop.quit)
        menu.exec_(global_pos)
        event_loop.exec_()

    def _expand_all(self):
        self.ui.column_view.expandAll()

    def _collapse_all(self):
        # Collapse all items
        self.ui.column_view.collapseAll()

    def _create_groups(self, group_dict):
        # Clear all rows from the model
        # self.column_view_model.clear()
        # Set up the column view
        self._setup_file_details_panel([])
        self._setup_column_view()

        # Add items to the model
        for category, sg_data in group_dict.items():
            # logger.debug(">>> category: {}, sg_data: {}".format(category, sg_data))
            category_item = QStandardItem(category)
            self.column_view_model.appendRow(category_item)
            for sg_list in sg_data:
                # logger.debug(">>> sg_list: {}".format(sg_list))
                tooltip = ""
                id = 0
                if sg_list and len(sg_list) >= 15:
                    id = sg_list[14]
                    base_name = sg_list[3]
                    if self._column_view_search_filter and len(self._column_view_search_filter) > 1:
                        prefix = self._column_view_search_filter
                        if not base_name.startswith(prefix):
                            # logger.debug(">>> skipping base_name: {}, prefix: {}".format(base_name, prefix))
                            continue
                    # Skip deleted files
                    action = sg_list[2]
                    if action and action in ["delete"]:
                        msg = "\n <span style='color:#2C93E2'>skipping deleted file: {}</span> \n".format(
                            base_name)
                        self._add_log(msg, 2)

                        continue
                    sg_item = self._column_view_dict.get(id, None)
                    tooltip = self._get_tooltip(sg_list, sg_item)
                item_list = []
                for col, value in enumerate(sg_list):
                    item = QStandardItem(str(value))
                    item.setToolTip(tooltip)
                    if col == 5:
                        item.setData(value, Qt.DisplayRole)
                    if col == 2:
                        action = sg_list[2]
                        # action_icon, icon_path = get_action_icon(action)
                        action_icon = self.actions_icons.get_icon_pixmap(action)
                        if action_icon:
                            item.setIcon(action_icon)
                    item.setData(str(id), QtCore.Qt.UserRole + 1)
                    item_list.append(item)

                category_item.appendRow(item_list)

        # Add a callback when someone clicks on an item in the view
        #self.ui.column_view.clicked.connect(self.on_column_view_item_clicked)

        self.ui.column_view.expandAll()


    def _get_sg_item_list_by_column_order(self, sg_item):
        if not sg_item:
            return [""]  # Fill the first column with an empty item
        column_order = ["", "folder", "action", "name", "revision", "size", "file_extension", "type", "user",
                        "task_name", "task_status", "step", "date", "date_modified", "publish_id", "description"]

        sg_list = []
        for attribute in column_order:
            value = sg_item.get(attribute, "")
            if attribute == "description" and value:
                # Get description from the beginning until the first line break
                value = value.split("\n")[0]
            sg_list.append(value)

        return sg_list

    def _populate_column_view_no_groups(self):
        """ Populate the table with data"""
        row = 0
        self._set_groups = False
        for id, sg_item in self._column_view_dict.items():
            if not sg_item:
                continue
            base_name = sg_item.get("name", None)
            if base_name and self._column_view_search_filter and len(self._column_view_search_filter) > 1:
                prefix = self._column_view_search_filter
                if not base_name.startswith(prefix):
                    # logger.debug(">>> skipping base_name: {}, prefix: {}".format(base_name, prefix))
                    continue
            # Skip deleted files
            action = sg_item.get("action") or sg_item.get("headAction") or None
            if action and action in ["delete"]:
                msg = "\n <span style='color:#2C93E2'>skipping deleted file: {}</span> \n".format(
                    base_name)
                self._add_log(msg, 2)
                continue
            if id in self._standard_item_dict:
                item_data = self._standard_item_dict[id]
                self._insert_perforce_row(row, item_data, sg_item)
                row += 1

    def _no_groups(self):
        # Clear all rows from the model
        #self.column_view_model.clear()
        # Set up the column view
        self._setup_column_view()
        self._current_column_view_grouping = self.COLUMN_VIEW_UNGROUP
        # Add items to the model
        self._populate_column_view_no_groups()

    def _group_by_folder(self):
        # self._group_by_folder_action.setCheckable(True)
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_FOLDER
        self._create_groups(self._folder_dict)

    def _group_by_action(self):
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_ACTION
        self._create_groups(self._action_dict)

    def _group_by_revision(self):
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_REVISION
        self._create_groups(self._revision_dict)

    def _group_by_file_extension(self):
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_EXTENSION
        self._create_groups(self._file_extension_dict)

    def _group_by_type(self):
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_TYPE
        self._create_groups(self._type_dict)

    def _group_by_user(self):
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_USER
        self._create_groups(self._user_dict)

    def _group_by_task_name(self):
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_TASK
        self._create_groups(self._task_name_dict)

    def _group_by_task_status(self):
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_STATUS
        self._create_groups(self._task_status_dict)

    def _group_by_step(self):
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_STEP
        self._create_groups(self._step_dict)

    def _group_by_date_modified(self):
        #self._setup_column_view()
        self._set_groups = True
        self._current_column_view_grouping = self.COLUMN_VIEW_GROUP_BY_DATE_MODIFIED
        self._create_groups(self._date_modified_dict)

    def _create_column_view_context_menu(self):
        self._column_add_action = QAction("Add", self.ui.column_view)
        self._column_add_action.triggered.connect(lambda: self._on_column_model_action("add"))
        self._column_edit_action = QAction("Edit", self.ui.column_view)
        self._column_edit_action.triggered.connect(lambda: self._on_column_model_action("edit"))
        self._column_delete_action = QAction("Delete", self.ui.column_view)
        self._column_delete_action.triggered.connect(lambda: self._on_column_model_action("delete"))

        self._column_revert_action = QAction("Revert", self.ui.column_view)
        self._column_revert_action.triggered.connect(lambda: self._on_column_model_action("revert"))

        #self._column_refresh_action = QAction("Refresh", self.ui.column_view)
        #self._column_refresh_action.triggered.connect(self._publish_model.async_refresh)

        self.ui.column_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.column_view.customContextMenuRequested.connect(
            self._show_column_actions
        )
    def _show_column_actions(self, pos):
        """
               Shows the actions for the current publish selection.

               :param pos: Local coordinates inside the viewport when the context menu was requested.
        """

        # Build a menu with all the actions.
        menu = QMenu(self)
        actions = self._action_manager.get_actions_for_publishes(
            self.selected_publishes, self._action_manager.UI_AREA_MAIN
        )
        menu.addActions(actions)

        # Qt is our friend here. If there are no actions available, the separator won't be added, yay!
        menu.addSeparator()
        menu.addAction(self._column_add_action)
        menu.addAction(self._column_edit_action)
        menu.addAction(self._column_delete_action)
        menu.addSeparator()
        menu.addAction(self._column_revert_action)
        menu.addSeparator()
        #menu.addAction(self._column_refresh_action)


        # Calculate the global position of the menu
        global_pos = self.ui.column_view.mapToGlobal(pos)

        # Execute the menu using a QEventLoop to block until an action is triggered
        event_loop = QEventLoop()
        menu.aboutToHide.connect(event_loop.quit)
        menu.exec_(global_pos)
        event_loop.exec_()



    def show_context_menu(self, pos):
        # Show the context menu at the cursor position
        selected_index = self.ui.column_view.indexAt(pos)
        if selected_index.isValid():
            source_index = self.perforce_proxy_model.mapToSource(selected_index)
            selected_row_data = self.get_row_data_from_source(source_index)
            if selected_row_data:
                self.context_menu.exec_(self.ui.column_view.mapToGlobal(pos))

    def get_row_data_from_source(self, source_index):
        # Get data from the source model using the source index
        row_data = []
        if source_index.isValid():
            row_number = source_index.row()
            for col in range(self.column_view_model.columnCount()):
                item = source_index.model().item(row_number, col)
                if item:
                    row_data.append(item.text())
        logger.debug("Row data: {}".format(row_data))
        return row_data


    def on_column_view_row_clicked(self, index):
        if self._set_groups:
            self.on_column_view_row_clicked_group(index)
        else:
            self.on_column_view_row_clicked_no_groups(index)

    def on_column_view_row_clicked_no_groups(self, index):
        source_index = self.perforce_proxy_model.mapToSource(index)
        row_number = source_index.row()
        # logger.debug(f"Clicked Row {row_number}")
        item = self.column_view_model.item(row_number, 14)  # Get the publish id from the 14th column
        if item:
            data = item.text()
            # Perform actions with the data from the clicked row
            # logger.debug(f"Clicked Row {row_number}, Data: {data}")
            if data and data != "N/A":
                id = int(data)
                self._setup_column_details_panel(id)

    def on_column_view_row_clicked_group(self, index):
        id_role = QtCore.Qt.UserRole + 1  # Custom role for "id"

        # Get the clicked item's index
        source_index = self.perforce_proxy_model.mapToSource(index)
        if source_index.isValid():
            # Get the "id" data from the custom role
            id = source_index.data(id_role)
            if id:
                id = int(id)
                # logger.debug(">>>>>>>>>>  id is: {}".format(id))
                # Perform actions using the retrieved "id"
                self._setup_column_details_panel(id)



    def _get_perforce_size(self, sg_data):
        """
        Get Perforce file size.
        """
        try:
            self._size_dict = {}
            for key in self._item_path_dict:
                if key:
                    #logger.debug(">>>>>>>>>>  key is: {}".format(key))
                    key = self._convert_local_to_depot(key).rstrip('/')
                    # Get the file size from Perforce for all revisions
                    #fstat_list = self._p4.run("fstat", "-T", "fileSize, clientFile, headRev", "-Of", "-Ol", key + '/...')
                    # Get the file size from Perforce
                    fstat_list = self._p4.run("fstat", "-T", "fileSize, clientFile", "-Ol", key + '/...')
                    #logger.debug(">>>>>>>>>>  fstat_list is: {}".format(fstat_list))
                    for fstat in fstat_list:
                        #if isinstance(fstat, list) and len(fstat) == 1:
                        #    fstat = fstat[0]
                        # logger.debug(">>>>>>>>>>  fstat is: {}".format(fstat))
                        if fstat:
                            size = fstat.get("fileSize", "N/A")
                            if size != "N/A":
                                size = "{:.2f}".format(int(size) / 1024 / 1024)
                                size = float(size)
                                # logger.debug(">>>>>>>>>>  size is: {}".format(size))
                            client_file = fstat.get('clientFile', None)

                            if client_file:
                                newkey = self._create_key(client_file)
                                #head_rev = fstat.get('headRev', "0")
                                #newkey = "{}#{}".format(newkey, head_rev)
                                if newkey:
                                    if newkey not in self._size_dict:
                                        self._size_dict[newkey] = {}
                                    self._size_dict[newkey]['fileSize'] = size
                    # logger.debug(">>>>>>>>>>  self._size_dict is: {}".format(self._size_dict))

                    for i, sg_item in enumerate(sg_data):

                        if "path" in sg_item:
                            if "local_path" in sg_item["path"]:
                                local_path = sg_item["path"].get("local_path", None)
                                modified_local_path = self._create_key(local_path)

                                if modified_local_path and modified_local_path in self._size_dict:
                                    if 'fileSize' in self._size_dict[modified_local_path]:
                                        sg_item["fileSize"] = self._size_dict[modified_local_path].get('fileSize', None)
                                # logger.debug(">>>>>>>>>>  sg_item is: {}".format(sg_item))
            # logger.debug(">>>>>>>>>>  sg_data is: {}".format(sg_data))
        except Exception as e:
            logger.debug("Error getting Perforce file size: {}".format(e))
            pass
        return sg_data



    def _insert_perforce_row(self, row, data, sg_item):
        tooltip = self._get_tooltip(data, sg_item)
        for col, value in enumerate(data):
            item = QStandardItem(str(value))
            item.setToolTip(tooltip)
            if col == 5:
                item.setData(value, Qt.DisplayRole)
            if col == 2:
                action = data[2]
                # action_icon, icon_path = get_action_icon(action)
                action_icon = self.actions_icons.get_icon_pixmap(action)
                if action_icon:
                    item.setIcon(action_icon)

            self.column_view_model.setItem(row, col, item)


    def print_selected_row(self):
        # Get the selected indexes from the column view
        selected_indexes = self.ui.column_view.selectionModel().selectedRows()

        if selected_indexes:
            for index in selected_indexes:
                row_number = index.row()
                print(f"Selected Row {row_number + 1}:")
                # You can access the data in each column of the selected row like this:
                for col in range(self.column_view_model.columnCount()):
                    item = self.column_view_model.item(row_number, col)
                    print(f"Column {col + 1}: {item.text()}")
        else:
            print("No rows selected.")

    def _on_column_model_action(self, action):
        if self._set_groups:
            self._on_column_model_action_groups(action)
        else:
            self._on_column_model_action_no_groups(action)

    def _on_column_model_action_no_groups(self, action):

        selected_actions = []
        selected_indexes = self.ui.column_view.selectionModel().selectedRows()
        for selected_index in selected_indexes:

            source_index = self.perforce_proxy_model.mapToSource(selected_index)
            selected_row_data = self.get_row_data_from_source(source_index)
            id = 0
            if (len(selected_row_data) >= 15):
                id = selected_row_data[14]

            sg_item = self._column_view_dict.get(int(id), None)
            # logger.debug("selected_row_data: {}".format(selected_row_data))

            if "path" in sg_item:
                if "local_path" in sg_item["path"]:
                    target_file = sg_item["path"].get("local_path", None)
                    depot_file = sg_item.get("depotFile", None)

                    if action in ["add", "move/add", "edit", "delete"]:
                        sg_item_action = sg_item.get("action", None)
                        if sg_item_action and sg_item_action == "delete":
                            msg = "Cannot perform the action on the file {} as it has already been marked for deletion or is deleted.".format(
                                depot_file)

                            self._add_log(msg, 2)

                        if action == "delete":
                            msg = "Marking file {} for deletion ...".format(depot_file)
                        else:
                            msg = "{} file {}".format(action, depot_file)
                        self._add_log(msg, 2)
                        selected_actions.append((sg_item, action))

                    elif action == "revert":
                        msg = "Revert file {} ...".format(target_file)
                        self._add_log(msg, 3)
                        # p4_result = self._p4.run("revert", "-v", target_file)
                        p4_result = self._p4.run("revert", target_file)
                        if p4_result:
                            self.refresh_publish_data()

        if selected_actions:
            self.perform_changelist_selection(selected_actions)

    def _on_column_model_action_groups(self, action):
        selected_actions = []
        selected_files_to_revert = []
        selected_indexes = self.ui.column_view.selectionModel().selectedRows()

        # Define the custom role for "id"
        id_role = QtCore.Qt.UserRole + 1

        for selected_index in selected_indexes:
            source_index = self.perforce_proxy_model.mapToSource(selected_index)
            if source_index.isValid():
                # Get the "id" data from the custom role
                id = source_index.data(id_role)
                if id is not None:
                    id = int(id)

                    sg_item = self._column_view_dict.get(id, None)
                    # logger.debug("Selected item's id: {}".format(id))

                    if "path" in sg_item:
                        if "local_path" in sg_item["path"]:
                            target_file = sg_item["path"].get("local_path", None)
                            depot_file = sg_item.get("depotFile", None)

                            if action in ["add", "move/add", "edit", "delete"]:
                                sg_item_action = sg_item.get("action", None)
                                if sg_item_action and sg_item_action == "delete":
                                    msg = "Cannot perform the action on the file {} as it has already been marked for deletion or is deleted.".format(
                                        depot_file)
                                    self._add_log(msg, 2)

                                if action == "delete":
                                    msg = "Marking file {} for deletion ...".format(depot_file)
                                else:
                                    msg = "{} file {}".format(action, depot_file)
                                self._add_log(msg, 2)
                                selected_actions.append((sg_item, action))


                            elif action == "revert":

                                # Collect files to revert instead of reverting immediately

                                if target_file:
                                    selected_files_to_revert.append(target_file)

                                    msg = "Preparing to revert file {} ...".format(target_file)

                                    self._add_log(msg, 3)
        # --- Perform bulk revert after the loop ---
        if action == "revert" and selected_files_to_revert:
            try:
                msg = f"Reverting {len(selected_files_to_revert)} selected file(s)..."
                self._add_log(msg, 2)
                # Use argument unpacking (*) to pass all files at once
                p4_result = self._p4.run("revert", *selected_files_to_revert)
                logger.debug(f"Bulk revert result: {p4_result}")
                if p4_result:  # Check if the command was successful (might need adjustment based on p4python output)
                    self.refresh_publish_data()  # Refresh data once after bulk operation
            except Exception as e:
                logger.error(f"Error during bulk revert: {e}")
                self._add_log(f"Error during bulk revert: {e}", 2)  # Show error in log window

        if selected_actions:
            self.perform_changelist_selection(selected_actions)


    def _get_tooltip(self, data, sg_item):
        """
        Gets a tooltip for this model item.

        :param item: ShotgunStandardItem associated with the publish.
        :param sg_item: Publish information from Shotgun.
        """
        #logger.debug(">>>>>>>>>>>> _set_tooltip: data: {}".format(data))
        #logger.debug(">>>>>>>>>>>> _set_tooltip: sg_item: {}".format(sg_item))
        tooltip = ""
        if not sg_item or not data:
            return tooltip
        tooltip += "<b>Name:</b> %s" % (sg_item.get("code") or "No name given.")

        # Version 012 by John Smith at 2014-02-23 10:34

        published_file_type = sg_item.get('type', None)
        if published_file_type in ['PublishedFile'] and data and len(data) >= 12:
            if sg_item.get("headAction"):
                tooltip += "<br><br><b>Head action:</b> %s" % (
                        sg_item.get("headAction") or "N/A"
                )
            if sg_item.get("action"):
                tooltip += "<br><br><b>Action:</b> %s" % (
                        sg_item.get("action") or "N/A"
                )

            tooltip += "<br><br><b>Revision:</b> #%s" % (
                    sg_item.get("revision") or "N/A"
            )

            tooltip += "<br><br><b>Size:</b> %s MB" % (
                (sg_item.get("fileSize") or "0")
            )

            tooltip += "<br><br><b>File Extension:</b> %s" % (
                (data[6] or "N/A")
            )
            tooltip += "<br><br><b>File Type:</b> %s" % (
                (data[7] or "N/A")
            )

            if not isinstance(sg_item.get("created_at"), datetime.datetime):
                created_unixtime = sg_item.get("created_at") or 0
                date_str = datetime.datetime.fromtimestamp(created_unixtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
            else:
                date_str = sg_item.get("created_at").strftime("%Y-%m-%d %H:%M")

            # created_by is set to None if the user has been deleted.
            if sg_item.get("created_by") and sg_item["created_by"].get("name"):
                author_str = sg_item["created_by"].get("name")
            else:
                author_str = "Unspecified User"

            version = sg_item.get("version_number")
            vers_str = "%03d" % version if version is not None else "N/A"

            tooltip += "<br><br><b>Version:</b> %s by %s at %s" % (
                vers_str,
                author_str,
                date_str,
            )

        tooltip += "<br><br><b>Task Name:</b> %s" % (
            (data[9] or "N/A")
        )

        tooltip += "<br><br><b>Task Status:</b> %s" % (
            (data[10] or "N/A")
        )

        tooltip += "<br><br><b>Path:</b> %s" % (
            (sg_item.get("path") or {}).get("local_path")
        )
        tooltip += "<br><br><b>Publish ID:</b> %s" % (
                sg_item.get("id") or "0"
        )
        tooltip += "<br><br><b>Description:</b> %s" % (
            sg_item.get("description") or "No description given."
        )


        if sg_item.get("headChange"):
            tooltip += "<br><br><b>Head change:</b> %s" % (
                    sg_item.get("headChange") or "N/A"
            )
        if sg_item.get("change"):
            tooltip += "<br><br><b>Change:</b> %s" % (
                    sg_item.get("change") or "N/A"
            )

        if sg_item.get("entity"):
            entity = sg_item.get("entity")
            if entity:
                entity_name = entity.get("name", "N/A")
                tooltip += "<br><br><b>Entity:</b> %s" % entity_name
                entity_id = entity.get("id", "N/A")
                tooltip += "<br><br><b>Entity ID:</b> %s" % entity_id

        return tooltip

    def _path_difference(self, path1, path2):
        # Normalize paths to use forward slashes and remove trailing slashes
        path1 = os.path.normpath(path1)
        path2 = os.path.normpath(path2)
        #logger.debug(">>>>>>>>>>>> path1: {}".format(path1))
        #logger.debug(">>>>>>>>>>>> path2: {}".format(path2))
        # Split paths into components
        components1 = path1.split(os.sep)
        components2 = path2.split(os.sep)
        #logger.debug(">>>>>>>>>>>> components1: {}".format(components1))
        #logger.debug(">>>>>>>>>>>> components2: {}".format(components2))

        # Find the common prefix
        common_prefix = []
        for component1, component2 in zip(components1, components2):
            if component1 == component2:
                common_prefix.append(component1)
            else:
                break

        # Calculate the difference by removing the common prefix
        #diff1 = components1[len(common_prefix):]
        diff2 = components2[len(common_prefix):]

        # Combine the difference components into a single path
        difference = os.sep.join(diff2)

        return difference

    def _print_sg_item(self, sg_item):
        for key, value in sg_item.items():
            msg = "{}: {}".format(key, value)
            logger.debug(msg)
    def _get_publish_icons(self):
        """
        Get the icons for the publish view.
        """
        total_file_count = 0
        self._publish_icons = {}

        model = self.ui.publish_view.model()
        for row in range(model.rowCount()):
            model_index = model.index(row, 0)
            proxy_model = model_index.model()
            source_index = proxy_model.mapToSource(model_index)
            # now we have arrived at our model derived from StandardItemModel
            # so let's retrieve the standarditem object associated with the index
            item = source_index.model().itemFromIndex(source_index)

            is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
            if not is_folder:
                # Run default action.
                total_file_count += 1
                sg_item = shotgun_model.get_sg_data(model_index)
                id = sg_item.get("id", None)
                icon = item.icon()
                if id and icon:
                    id = int(id)
                    self._publish_icons[id] = icon

    def _setup_column_details_panel(self, id):
        """
        Sets up the file details panel with info for a given column view row.
        """

        def __make_table_row(left, right):
            """
            Helper method to make a detail table row
            """
            return (
                "<tr><td><b style='color:#2C93E2'>%s</b>&nbsp;</td><td>%s</td></tr>"
                % (left, right)
            )

        def __set_publish_ui_visibility(is_publish):
            """
            Helper method to enable disable publish specific details UI
            """
            # disable version file_history stuff
            self.ui.version_file_history_label.setEnabled(is_publish)
            self.ui.file_history_view.setEnabled(is_publish)

            # hide actions and playback stuff
            self.ui.file_detail_actions_btn.setVisible(is_publish)
            self.ui.file_detail_playback_btn.setVisible(is_publish)


        def __clear_publish_file_history(pixmap):
            """
            Helper method that clears the file_history view on the right hand side.

            :param pixmap: image to set at the top of the file_history view.
            """
            self._publish_file_history_model.clear()
            self.ui.file_details_header.setText("")
            self.ui.file_details_image.setPixmap(pixmap)
            __set_publish_ui_visibility(False)

        # note - before the UI has been shown, querying isVisible on the actual
        # widget doesn't work here so use member variable to track state instead
        if not self._details_pane_visible:
            logger.debug("Detailed pan is not visible")
            return

        selected_indexes = self.ui.column_view.selectionModel().selectedRows()
        if selected_indexes and len(selected_indexes) > 1:
            logger.debug("More than one row selected")
            __clear_publish_file_history(self._multiple_publishes_pixmap)
            return

        if id == 0:
            logger.debug("ID is 0")
            __clear_publish_file_history(self._no_selection_pixmap)

        else:
            if id not in self._column_view_dict:
                logger.debug("id is not available in the column view")
                __clear_publish_file_history(self._no_selection_pixmap)
                __set_publish_ui_visibility(False)
                return
            else:

                sg_item = self._column_view_dict[id]
                if not sg_item:
                    logger.debug("sg_item is empty")
                    __clear_publish_file_history(self._no_selection_pixmap)
                    __set_publish_ui_visibility(False)
                    return
                publish_type = sg_item.get("type", None)
                if publish_type not in ["PublishedFile"]:
                    logger.debug("Type is not PublishedFile")
                    __clear_publish_file_history(self._no_selection_pixmap)
                    __set_publish_ui_visibility(False)
                    return

                __set_publish_ui_visibility(True)
                """
                import urllib.request

                image_data = sg_item.get('image', None)
                
                if image_data:
                    # Define the local path to save the image
                    local_image_path = "/temp/path_to_save_local_image.png"  # Replace with the desired local path

                    # Save the downloaded image data to the local file
                    with open(local_image_path, "wb") as local_image_file:
                        local_image_file.write(image_data)

                self.ui.file_details_image.setPixmap(QPixmap(local_image_path))
                """

                if self._publish_icons and id in self._publish_icons:
                    thumb_pixmap = self._publish_icons[id].pixmap(512)
                    self.ui.file_details_image.setPixmap(thumb_pixmap)

                # thumb_pixmap = item.icon().pixmap(512)
                # self.ui.file_details_image.setPixmap(thumb_pixmap)


                # sort out the actions button
                actions = self._action_manager.get_actions_for_publish(
                    sg_item, self._action_manager.UI_AREA_DETAILS
                )
                if len(actions) == 0:
                    self.ui.file_detail_actions_btn.setVisible(False)
                else:
                    self.ui.file_detail_playback_btn.setVisible(True)
                    self._file_details_action_menu.clear()
                    for a in actions:
                        self._dynamic_widgets.append(a)
                        self._file_details_action_menu.addAction(a)

                # if there is an associated version, show the play button
                if sg_item.get("version"):
                    sg_url = sgtk.platform.current_bundle().shotgun.base_url
                    url = "%s/page/media_center?type=Version&id=%d" % (
                        sg_url,
                        sg_item["version"]["id"],
                    )

                    self.ui.file_detail_playback_btn.setVisible(True)
                    self._current_version_detail_playback_url = url
                else:
                    self.ui.file_detail_playback_btn.setVisible(False)
                    self._current_version_detail_playback_url = None

                if sg_item.get("name") is None:
                    name_str = "No Name"
                else:
                    name_str = sg_item.get("name")

                #type_str = shotgun_model.get_sanitized_data(
                #    item, SgLatestPublishModel.PUBLISH_TYPE_NAME_ROLE
                #)
                type_str = sg_item.get("type")
                msg = ""
                msg += __make_table_row("Name", name_str)
                msg += __make_table_row("Type", type_str)

                version = sg_item.get("version_number")
                vers_str = "%03d" % version if version is not None else "N/A"

                msg += __make_table_row("Version", "%s" % vers_str)

                if sg_item.get("entity"):
                    display_name = shotgun_globals.get_type_display_name(
                        sg_item.get("entity").get("type")
                    )
                    entity_str = "<b>%s</b> %s" % (
                        display_name,
                        sg_item.get("entity").get("name"),
                    )
                    msg += __make_table_row("Link", entity_str)

                # sort out the task label
                if sg_item.get("task"):

                    if sg_item.get("task.Task.content") is None:
                        task_name_str = "Unnamed"
                    else:
                        task_name_str = sg_item.get("task.Task.content")

                    if sg_item.get("task.Task.sg_status_list") is None:
                        task_status_str = "No Status"
                    else:
                        task_status_code = sg_item.get("task.Task.sg_status_list")
                        task_status_str = self._status_model.get_long_name(
                            task_status_code
                        )

                    msg += __make_table_row(
                        "Task", "%s (%s)" % (task_name_str, task_status_str)
                    )

                # if there is a version associated, get the status for this
                if sg_item.get("version.Version.sg_status_list"):
                    task_status_code = sg_item.get("version.Version.sg_status_list")
                    task_status_str = self._status_model.get_long_name(task_status_code)
                    msg += __make_table_row("Review", task_status_str)

                if sg_item.get("revision"):
                    revision = sg_item.get("revision")
                    msg += __make_table_row("Revision#", revision)

                if sg_item.get("action"):
                    action = sg_item.get("action")
                    msg += __make_table_row("Action", action)
                else:
                    if sg_item.get("headAction"):
                        head_action = sg_item.get("headAction", "N/A")
                        msg += __make_table_row("Action", head_action)


                self.ui.file_details_header.setText("<table>%s</table>" % msg)

                # tell details pane to load stuff
                self._publish_file_history_model.load_data(sg_item)

            self.ui.file_details_header.updateGeometry()
    #############################################################################################################

    def _populate_submitted_widget(self):

        self.ui.submitted_scroll.setVisible(True)
        self._reset_submitted_widget()
        msg = "\n <span style='color:#2C93E2'>Updating data ...</span> \n"
        self._add_log(msg, 2)
        #logger.debug(">>>>>>>>>>  update_fstat_data...")
        self._update_fstat_data()
        # logger.debug(">>>>>>>>>>  Updating self._fstat_dict is: {}")
        # for key, sg_item in self._fstat_dict.items():
        #    logger.debug("{}:{}".format(key, sg_item))
        #logger.debug(">>>>>>>>>>  fix_fstat_dict...")
        self._fix_fstat_dict()

        length = len(self._fstat_dict)
        if length > 0:
            msg = "\n <span style='color:#2C93E2'>Populating the submitted view with {} files. Please wait...</span> \n".format(
                length)
            self._add_log(msg, 2)
            self.submitted_tree_view = TreeViewWidget(data_dict=self._fstat_dict, sorted=False, mode="submitted",
                                                      p4=self._p4)
            self.submitted_tree_view.populate_treeview_widget_submitted()
            publish_widget = self.submitted_tree_view.get_treeview_widget()

            # Submitted Scroll Area
            self.ui.submitted_scroll.setWidget(publish_widget)
            # self.ui.submitted_scroll.setVisible(True)
            #logger.debug(">>> Updating submitted_tree_view is complete")

            msg = "\n <span style='color:#2C93E2'>Select files in the Submitted view then click <i>Fix Selected</i> or click <i>Fix All</i> to publish them using the <i>Shotgrid Publisher</i>...</span> \n"
            self._add_log(msg, 2)

    def _reset_submitted_widget(self):
        null_widget = SWCTreeView()
        self.ui.submitted_scroll.setWidget(null_widget)

    def update_pending_view(self):
        """
        Shows the pending view
        """
        self._change_dict = {}
        self._get_default_changelists()
        self._get_pending_changelists()

        # publish_widget, self._pending_publish_list = self._create_perforce_ui(self._change_dict, sorted=True)
        self.pending_tree_view = TreeViewWidget(data_dict=self._change_dict, sorted=True, mode="pending", p4=self._p4)
        self.pending_tree_view.populate_treeview_widget_pending()
        publish_widget = self.pending_tree_view.get_treeview_widget()
        # Pending Scroll Area
        self.ui.pending_scroll.setWidget(publish_widget)



    def _turn_all_modes_off(self):
        self.ui.publish_view.setVisible(False)
        self.ui.column_view.setVisible(False)
        self.ui.perforce_scroll.setVisible(False)
        self.ui.submitted_scroll.setVisible(False)
        self.ui.pending_scroll.setVisible(False)

        self.ui.thumbnail_mode.setChecked(False)
        self.ui.list_mode.setChecked(False)
        self.ui.column_mode.setChecked(False)
        self.ui.submitted_mode.setChecked(False)
        self.ui.pending_mode.setChecked(False)

        self.ui.list_mode.setIcon(
            QIcon(QPixmap(":/res/mode_switch_card.png"))
        )
        self.ui.thumbnail_mode.setIcon(
            QIcon(QPixmap(":/res/mode_switch_thumb.png"))
        )
        self.ui.column_mode.setIcon(
            QIcon(QPixmap(":/res/mode_switch_column.png"))
        )
        """
        self.ui.submitted_mode.setIcon(
            QIcon(QPixmap(":/res/mode_switch_thumb.png"))
        )
        self.ui.pending_mode.setIcon(
            QIcon(QPixmap(":/res/mode_switch_card.png"))
        )
        """


        repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

        inactive_column_view_image_path = os.path.join(repo_root, "icons/mode_switch_column_off.png")
        inactive_column_view_icon = QIcon(QPixmap(inactive_column_view_image_path))

        inactive_submitted_image_path = os.path.join(repo_root, "icons/submitted_off.png")
        submitted_icon_inactive = QIcon(QPixmap(inactive_submitted_image_path))

        inactive_pending_image_path = os.path.join(repo_root, "icons/pending_off.png")
        pending_icon_inactive = QIcon(QPixmap(inactive_pending_image_path))

        perforce_publish_image_path = os.path.join(repo_root, "icons/perforce_1.png")
        perforce_publish_icon = QIcon(QPixmap(perforce_publish_image_path))

        self.ui.column_mode.setIcon(inactive_column_view_icon)
        self.ui.submitted_mode.setIcon(submitted_icon_inactive)
        self.ui.pending_mode.setIcon(pending_icon_inactive)
        self._show_thumb_scale(False)

    def _show_thumb_scale(self, is_visible):
        """
        Shows or hides the scale widgets.

        :param bool is_visible: If True, scale slider will be shown.
        """
        self.ui.thumb_scale.setVisible(is_visible)
        self.ui.scale_label.setVisible(is_visible)

    def _toggle_details_pane(self):
        """
        Executed when someone clicks the show/hide details button
        """
        if self.ui.details_tab.isVisible():
            self._set_details_pane_visiblity(False)
        else:
            self._set_details_pane_visiblity(True)

    def _set_details_pane_visiblity(self, visible):
        """
        Specifies if the details pane should be visible or not
        """
        # store our value in a setting
        self._settings_manager.store("show_details", visible)

        if visible == False:
            # hide details pane
            self._details_pane_visible = False
            self.ui.details_tab.setVisible(False)
            self.ui.info.setText("Show Details")

        else:
            # show details pane
            self._details_pane_visible = True
            self.ui.details_tab.setVisible(True)
            self.ui.info.setText("Hide Details")

            # if there is something selected, make sure the detail
            # section is focused on this
            selection_model = self.ui.publish_view.selectionModel()

            self._setup_file_details_panel(selection_model.selectedIndexes())

    def _setup_entity_details_panel(self, entity_data, item):
        """
        Sets up the entity details panel with info for a given item.
        """

        def __make_table_row(left, right):
            """
            Helper method to make a detail table row
            """
            return (
                    "<tr><td><b style='color:#2C93E2'>%s</b>&nbsp;</td><td>%s</td></tr>"
                    % (left, right)
            )
        if entity_data:
            entity_name = entity_data.get("code", None)
            entity_type = entity_data.get("type", None)
            entity_id = entity_data.get("id", None)
            for field in entity_data.keys():
                if "image" in field and entity_data[field] is not None:
                    image_url = entity_data.get(field)
                    logger.debug("Image url: %s" % image_url)
                    thumb_pixmap = QPixmap.fromImage(image_url)
                    self.ui.entity_details_image.setPixmap(thumb_pixmap)
                    #self._request_thumbnail_download(self, item, field, image_url, entity_type, entity_id)
                    """
                    image_path = os.path.join(self._temp_dir, "asset_image.jpg")
                    logger.debug("Downloading image %s to %s" % (image_url, image_path))
                    self._app.shotgun.download_attachment(image_url, image_path)
                    thumb_pixmap = QPixmap(image_path)
                    self.ui.entity_details_image.setPixmap(thumb_pixmap)
                    """

            msg = ""

            if entity_name:
                msg += __make_table_row("Name", "%s" % entity_name)

            if entity_type:
                msg += __make_table_row("Type", "%s" % entity_type)

            if entity_id:
                msg += __make_table_row("ID", "%s" % entity_id)

            entity_status = entity_data.get("sg_status_list", None)
            if entity_status:
                msg += __make_table_row("Status", "%s" % entity_status)

            entity_description = entity_data.get("description", None)
            if entity_description:
                # get the first 30 chars of the description
                entity_description = entity_description[:30]
                msg += __make_table_row("Description", "%s" % entity_description)

            entity_asset_library_dict = entity_data.get("sg_asset_library", None)
            if entity_asset_library_dict:
                entity_asset_library = entity_asset_library_dict.get("name", None)
                if entity_asset_library:
                    msg += __make_table_row("Asset Library", "%s" % entity_asset_library)

            entity_asset_type = entity_data.get("sg_asset_type", None)
            if entity_asset_type:
                msg += __make_table_row("Asset Type", "%s" % entity_asset_type)

            # self.ui.entity_details_header.setText("<table>%s</table>" % msg)
            """
            # sort out the actions button
            actions = self._action_manager.get_actions_for_publish(
                entity_data, self._action_manager.UI_AREA_DETAILS
            )
            if len(actions) == 0:
                self.ui.entity_detail_actions_btn.setVisible(False)
            else:
                self.ui.entity_detail_actions_btn.setVisible(True)
                self._entity_details_action_menu.clear()
                for a in actions:
                    self._dynamic_widgets.append(a)
                    self._entity_details_action_menu.addAction(a)
            """
    def _request_thumbnail_download(self, item, field, url, entity_type, entity_id):
        """
        Request that a thumbnail is downloaded for an item. If a thumbnail is successfully
        retrieved, either from disk (cached) or via shotgun, the method _populate_thumbnail()
        will be called. If you want to control exactly how your shotgun thumbnail is
        to appear in the UI, you can subclass this method. For example, you can subclass
        this method and perform image composition prior to the image being added to
        the item object.

        .. note:: This is an advanced method which you can use if you want to load thumbnail
            data other than the standard 'image' field. If that's what you need, simply make
            sure that you set the download_thumbs parameter to true when you create the model
            and standard thumbnails will be automatically downloaded. This method is either used
            for linked thumb fields or if you want to download thumbnails for external model data
            that doesn't come from Shotgun.

        :param item: :class:`~PySide.QStandardItem` which belongs to this model
        :param field: Shotgun field where the thumbnail is stored. This is typically ``image`` but
                      can also for example be ``sg_sequence.Sequence.image``.
        :param url: thumbnail url
        :param entity_type: Shotgun entity type
        :param entity_id: Shotgun entity id
        """
        if url is None:
            # nothing to download. bad input. gracefully ignore this request.
            return

        if not self._sg_data_retriever:
            raise sgtk.ShotgunModelError("Data retriever is not available!")

        uid = self._sg_data_retriever.request_thumbnail(
            url, entity_type, entity_id, field, self.__bg_load_thumbs
        )

        # keep tabs of this and call out later - note that we use a weakref to allow
        # the model item to be gc'd if it's removed from the model before the thumb
        # request completes.
        self.__thumb_map[uid] = {"item_ref": weakref.ref(item), "field": field}


    def __bg_load_thumbs(self, uid, thumb_path):
        """
        Callback from the data retriever when a thumbnail has been downloaded.
        """
        # get the item ref
        item_ref = self.__thumb_map[uid]["item_ref"]
        field = self.__thumb_map[uid]["field"]
        del self.__thumb_map[uid]

        # get the item
        item = item_ref()
        if not item:
            # item has been removed from the model
            return

        # populate the thumbnail
        self._populate_thumbnail(item, field, thumb_path)

    def _get_entity_parents_new(self, entity_data):
        """
        Get the entity parents for a given item.
        :param entity_data:
        :return:
        """
        self.entity_parents = []
        if entity_data:
            entity_id = entity_data.get("id", None)
            entity_type = entity_data.get("type", None)

            if entity_id and entity_type:
                filters = [["id", "is", entity_id]]
                fields = ["id", "code", "type", "parents"]

                # Get the entity
                published_entities = self._app.shotgun.find(entity_type, filters, fields)

                #logger.debug(">>>>>>>>>>> Published entity: %s" % published_entities)
                for published_entity in published_entities:
                    # Get the parents
                    linked_assets = published_entity.get("parents", None)
                    if linked_assets:
                        for parent in linked_assets:
                            self.entity_parents.append(parent)

                #logger.debug(">>>>>>>>>>> Parents: %s" % self.entity_parents)
                for entity_parent in self.entity_parents:
                    entity_path, entity_id, entity_type = self._get_entity_info(entity_parent)
                    entity_parent["entity_path"] = entity_path

                #logger.debug(">>>>>>>>>>> Parents with paths: %s" % self.entity_parents)

    def _get_entity_parents(self, entity_data):
        """
        Get the entity parents for a given item.
        :param entity_data:
        :return:
        """
        self.entity_parents = []
        if entity_data:
            entity_id = entity_data.get("id", None)
            entity_type = entity_data.get("type", None)
            if "entity" in entity_data:
                entity_info = entity_data.get("entity", None)
                if entity_info:
                    # get the entity id
                    entity_id = entity_info.get("id", None)
                    # get the entity type
                    entity_type =entity_info.get("type", None)


            if entity_id and entity_type:
                filters = [["id", "is", entity_id]]
                fields = ["id", "code", "type", "parents", "sg_asset_parent", "project", "sg_status_list"]
                #fields = ["id", "code", "type", "parents", "sg_asset_parent", "sg_assets", "project",
                #          "sg_asset_library", "asset_section", "asset_category", "sg_asset_type", "sg_status_list"]

                # get the entity
                published_entities = self._app.shotgun.find(entity_type, filters, fields)

                #logger.debug(">>>>>>>>>>> Published entity: %s" % published_entities)
                for published_entity in published_entities:
                    # get the asset parent
                    asset_parent = published_entity.get("sg_asset_parent", None)
                    #logger.debug(">>>>>>>>>>>sg_asset_parent: %s" % asset_parent)
                    if asset_parent:
                        self.entity_parents.append(asset_parent)
                    # get the parents
                    linked_assets = published_entity.get("parents", None)
                    if linked_assets:
                        for parent in linked_assets:
                            self.entity_parents.append(parent)

                #logger.debug(">>>>>>>>>>>Parents: %s" % self.entity_parents)
                for entity_parent in self.entity_parents:
                    entity_path, entity_id, entity_type = self._get_entity_info(entity_parent)
                    entity_parent["entity_path"] = entity_path
                logger.debug("Parents with paths: %s" % self.entity_parents)


    def _setup_entity_parent_and_children(self, entity_data):
        """
        Sets up the entity parents and children panel with info for a given item.
        :param entity_data:
        :return:
        """
        self.entity_parents = []
        self.entity_children = []
        if entity_data:
            # get the entity id
            entity_id = entity_data.get("id", None)
            # get the entity type
            entity_type = entity_data.get("type", None)
            if entity_id and entity_type:
                filters = [["id", "is", entity_id]]
                #fields = ["id", "code", "type", "parents", "sg_asset_parent", "sg_assets", "sg_asset_library", "asset_section", "asset_category", "sg_asset_type", "sg_status_list"]
                fields = ["id", "code", "type", "parents", "sg_asset_parent", "sg_assets", "project", "sg_asset_library", "asset_section", "asset_category", "sg_asset_type", "sg_status_list"]

                # get the entity
                published_entity = self._app.shotgun.find_one(entity_type, filters, fields)
                # get the asset parent
                asset_parents = published_entity.get("sg_asset_parent", None)
                # get the parents
                linked_assets = published_entity.get("parents", None)
                # combine the parents
                self.entity_parents = asset_parents + linked_assets if asset_parents and linked_assets else asset_parents or linked_assets

                # Get the children
                self.entity_children = published_entity.get("sg_assets", None)

                #logger.debug(">>>>>>>>>>> Published entity: %s" % published_entity)
                #logger.debug(">>>>>>>>>>> Asset Parent: %s" % asset_parents)
                #logger.debug(">>>>>>>>>>> Linked Assets: %s" % linked_assets)
                #logger.debug(">>>>>>>>>>>Parents: %s" % self.entity_parents)
                #logger.debug(">>>>>>>>>>> Asset Children: %s" % self.entity_children)

                self._populate_parents_tab(self.entity_parents)
                self._populate_children_tab(self.entity_children)

    def _populate_parents_tab(self, parents):
        """ Populate the parents tab with the parent entities of the selected entity"""
        parent_publish_files = self._get_parents_publish_files()
        if parent_publish_files:
            self._set_entity_tabs_ui_visibility(True)
            for parent_publish_file in parent_publish_files:
                self._load_publishes_for_parents_entity(self, parent_publish_file) 
                self._publish_entity_parents_model.load_data(parent_publish_file)

        """

        parents_item_list = []
        if parents:
            for parent in parents:
                if parent:
                    # get the entity id
                    entity_id = parent.get("id", None)
                    # get the entity type
                    entity_type = parent.get("type", None)
                    if entity_id and entity_type:

                        filters = [["id", "is", entity_id]]
                        fields = ["id", "code", "type", "parents", "sg_asset_parent", "sg_assets", "project", "name", 'image',
                                  "path", "task", "publish_type_field", 'published_file_type', 'created_by', 'created_at',
                                  "sg_asset_library", "asset_section", "asset_category", "sg_asset_type", "sg_status_list"]

                        # get the entity
                        published_entity = self._app.shotgun.find_one(entity_type, filters, fields)

                        if not published_entity:
                            continue

                        # Get the name from published_entity, if not available, use parent's "name" or "code"
                        published_entity["name"] = published_entity.get("name") or parent.get("name") or parent.get("code", "No Name")

                        # Get the task from published_entity, if not available, use parent's "task"
                        published_entity["task"] = published_entity.get("task") or parent.get("task") or None

                        # Get the entity from published_entity, if not available, use parent's "entity"
                        published_entity["entity"] = published_entity.get("entity") or parent.get("entity") or None

                        # Get the publish_type_field from published_entity, if not available, use parent's "publish_type_field"
                        published_entity["publish_type_field"] = published_entity.get("publish_type_field") or parent.get("publish_type_field") or None

                        # Get the published_file_type from published_entity, if not available, use parent's "published_file_type"
                        published_entity["published_file_type"] = published_entity.get("published_file_type") or parent.get("published_file_type") or None

                        # logger.debug(">>>>>>>>>>> Parent Published entity: %s" % published_entity)

                        parents_item_list.append(published_entity)

        # load the parents into the model
        self.ui.entity_parents_view.selectionModel().clear()
        if parents_item_list:
            self.ui.entity_parents_view.setEnabled(True)
            for parent_item in parents_item_list:
                self._load_publishes_for_parents_entity(parent_item)
        """



    def _set_entity_tabs_ui_visibility(self, is_publish):
            """
            Helper method to enable disable publish specific details UI
            """

            #self.ui.version_file_history_label.setEnabled(is_publish)
            #self.ui.file_history_view.setEnabled(is_publish)
            self.ui.entity_parents_view.setEnabled(is_publish)
            self.ui.entity_children_view.setEnabled(is_publish)

            # hide actions and playback stuff
            #self.ui.file_detail_actions_btn.setVisible(is_publish)
            #self.ui.file_detail_playback_btn.setVisible(is_publish)

    def _populate_children_tab(self, children):
        """ Populate the children tab with the child entities of the selected entity"""

        children_publish_files = self._get_children_publish_files()
        if children_publish_files:
            self._set_entity_tabs_ui_visibility(True)
            for child_publish_file in children_publish_files:
                self._publish_entity_children_model.load_data(child_publish_file)
        """
        children_item_list = []
        for child in children:
            if child:
                # get the entity id
                entity_id = child.get("id", None)
                # get the entity type
                entity_type = child.get("type", None)
                if entity_id and entity_type:
                    filters = [["id", "is", entity_id]]
                    fields = ["id", "code", "type", "parents", "sg_asset_parent", "sg_assets", "project", "name", 'image',
                              "path", "task", "publish_type_field", 'published_file_type', 'created_by', 'created_at',
                              "sg_asset_library", "asset_section", "asset_category", "sg_asset_type", "sg_status_list"]

                    # get the entity
                    published_entity = self._app.shotgun.find_one(entity_type, filters, fields)
                    if not published_entity:
                        continue

                   # Get the name from published_entity, if not available, use child's "name" or "code"
                    published_entity["name"] = published_entity.get("name") or child.get("name") or child.get("code", "No Name")

                    # Get the task from published_entity, if not available, use child's "task"
                    published_entity["task"] = published_entity.get("task") or child.get("task") or None

                    # Get the entity from published_entity, if not available, use child's "entity"
                    published_entity["entity"] = published_entity.get("entity") or child.get("entity") or None

                    # Get the publish_type_field from published_entity, if not available, use `publish_type_field` from child
                    published_entity["publish_type_field"] = published_entity.get("publish_type_field") or child.get("publish_type_field") or None

                    # Get the published_file_type from published_entity, if not available, use `published_file_type` from child
                    published_entity["published_file_type"] = published_entity.get("published_file_type") or child.get("published_file_type") or None

                    # logger.debug(">>>>>>>>>>> Child Published entity: %s" % published_entity)
                    children_item_list.append(published_entity)

            # load the children into the model
            self.ui.entity_children_view.selectionModel().clear()
            if children_item_list:
                self.ui.entity_children_view.setEnabled(True)
                for child_item in children_item_list:
                    self._load_publishes_for_children_entity(child_item)
        """


    def _get_parents_publish_files(self):
        """ Get the published files for the parents of the selected entity"""
        self.entity_parents_published_files_list = []
        for parent in self.entity_parents:
            if parent:
                parent_type = parent.get("type", None)
                parent_id = parent.get("id", None)
                if parent_id and parent_type:
                    filters = [["entity", "is", {"type": parent_type, "id": parent_id}]]
                    fields = ["id", "code", "type", "entity", "project", "name", "path", "path",
                              "publish_type_field", 'published_file_type', 'created_by', 'created_at']
                    # fields = ["id", "code", "type", "entity","project","name", "image", "path","path", "task",
                    #          "publish_type_field", 'published_file_type', 'created_by', 'created_at', "sg_status_list"]
                    published_files = self._app.shotgun.find("PublishedFile", filters, fields)
                    self.entity_parents_published_files_list.extend(published_files)
        #logger.debug(">>>>>>>>>>> Entity parents Published Files: ")

        return self.entity_parents_published_files_list


    def _get_children_publish_files(self):
        """ Get the published files for the children of the selected entity"""
        self.entity_children_published_files_list = []
        for child in self.entity_children:
            if child:
                child_type = child.get("type", None)
                child_id = child.get("id", None)
                if child_id and child_type:
                    filters = [["entity", "is", {"type": child_type, "id": child_id}]]
                    fields = ["id", "code", "type", "entity", "parents", "sg_asset_parent", "sg_assets", "project", "name", "image",
                              "path", "task", "publish_type_field", 'published_file_type', 'created_by', 'created_at',
                              "sg_asset_library", "asset_section", "asset_category", "sg_asset_type", "sg_status_list"]
                    published_files = self._app.shotgun.find("PublishedFile", filters, fields)
                    self.entity_children_published_files_list.extend(published_files)


        # logger.debug(">>>>>>>>>>> Entity children Published Files: %s" % self.entity_children_published_files_list)
        return self.entity_children_published_files_list

    def _prepare_entity_parents_published_files(self):
        """ Sync the published files for the parents of the selected entity"""
        self._get_parents_publish_files()
        # logger.debug(">>>>>>>>>>> Entity parents Published Files: {}".format(self.entity_parents_published_files_list))
        files_to_sync = []
        msg = "\n <span style='color:#2C93E2'>Preparing entity parents files...</span> \n"
        self._add_log(msg, 2)
        for published_file in self.entity_parents_published_files_list:
            if 'path' in published_file:
                local_path = published_file['path'].get('local_path', None)
                if local_path in files_to_sync:
                    continue
                if local_path:
                    head_rev = published_file.get('headRev', None)
                    have_rev = published_file.get('haveRev', None)
                    try:
                        code = published_file.get('code', None)
                        if code:
                            code = code.split("#")[-1]
                        msg = "Checking file {}#{}".format(local_path, code)
                        # msg = "Checking file {}".format(local_path)
                        self._add_log(msg, 4)
                    except:
                        pass

                    # logger.debug(">>>>>>>>>>> (1) head_rev:{} have_rev:{}".format(head_rev, have_rev))
                    if not head_rev and not have_rev:
                        # fstat_list = self._p4.run_fstat(local_path + '/...')
                        fstat_list = self._p4.run_fstat(local_path)
                        # logger.debug(">>>>>>>>>>> fstat_list:{}".format(fstat_list))
                        if fstat_list:
                            for file_info in fstat_list:
                                if file_info:
                                    if isinstance(file_info, list) and len(file_info) == 1:
                                        file_info = file_info[0]
                                    # logger.debug(">>>>>>>>>>> file_info:{}".format(file_info))
                                    head_rev = file_info.get('headRev', None)
                                    have_rev = file_info.get('haveRev', None)
                                    # logger.debug(">>>>>>>>>>> (2) head_rev:{} have_rev:{}".format(head_rev, have_rev))
                                    published_file["headRev"] = head_rev
                                    published_file["haveRev"] = have_rev
                        # logger.debug(">>>>>>>>>>> (3) head_rev:{} have_rev:{}".format(head_rev, have_rev))
                    if head_rev:
                        if not have_rev:
                            have_rev = "0"
                        if self._to_sync(have_rev, head_rev):
                            if local_path not in files_to_sync:
                                files_to_sync.append(local_path)


        return files_to_sync

    def _sync_entity_parents_published_files(self):
        """ Sync the published files for the parents of the selected entity"""
        files_to_sync = self._prepare_entity_parents_published_files()
        logger.debug(">>>>>>>>>>> Parent files to sync:{}".format(files_to_sync))

        files_to_sync_count = len(files_to_sync)
        if files_to_sync_count == 0:
            msg = "\n <span style='color:#2C93E2'>No file sync required for entity parents.</span> \n"
            self._add_log(msg, 2)

        elif files_to_sync_count > 0:

            msg = "\n <span style='color:#2C93E2'>Syncing {} published files of entity parents.... </span> \n".format(files_to_sync_count)
            self._add_log(msg, 2)
            self._do_sync_files_threading_thread_2(files_to_sync, entity=True)

            msg = "\n <span style='color:#2C93E2'>Syncing entity parents published files is complete</span> \n"
            self._add_log(msg, 2)

    def _prepare_entity_children_published_files(self):
        """ Sync the published files for the children of the selected entity"""
        self._get_children_publish_files()
        files_to_sync = []
        msg = "\n <span style='color:#2C93E2'>Preparing entity children files...</span> \n"
        self._add_log(msg, 2)
        for published_file in self.entity_children_published_files_list:
            if 'path' in published_file:
                local_path = published_file['path'].get('local_path', None)
                if local_path:
                    msg = "Checking file {}".format(local_path)
                    self._add_log(msg, 4)
                    head_rev = published_file.get('headRev', None)
                    have_rev = published_file.get('haveRev', None)
                    # logger.debug(">>>>>>>>>>> (1) head_rev:{} have_rev:{}".format(head_rev, have_rev))
                    if not head_rev and not have_rev:
                        # fstat_list = self._p4.run_fstat(local_path + '/...')
                        fstat_list = self._p4.run_fstat(local_path)
                        # logger.debug(">>>>>>>>>>> fstat_list:{}".format(fstat_list))
                        if fstat_list:
                            for file_info in fstat_list:
                                if file_info:
                                    if isinstance(file_info, list) and len(file_info) == 1:
                                        file_info = file_info[0]
                                    # logger.debug(">>>>>>>>>>> file_info:{}".format(file_info))
                                    head_rev = file_info.get('headRev', None)
                                    have_rev = file_info.get('haveRev', None)
                                    # logger.debug(">>>>>>>>>>> (2) head_rev:{} have_rev:{}".format(head_rev, have_rev))
                                    published_file["headRev"] = head_rev
                                    published_file["haveRev"] = have_rev
                        # logger.debug(">>>>>>>>>>> (3) head_rev:{} have_rev:{}".format(head_rev, have_rev))
                    if head_rev:
                        if not have_rev:
                            have_rev = "0"
                        if self._to_sync(have_rev, head_rev):
                            files_to_sync.append(local_path)

        return files_to_sync

    def _sync_entity_children_published_files(self):
        """ Sync the published files for the children of the selected entity"""
        files_to_sync = self._prepare_entity_children_published_files()

        files_to_sync_count = len(files_to_sync)
        if files_to_sync_count == 0:
            msg = "\n <span style='color:#2C93E2'>No file sync required for entity children.</span> \n"
            self._add_log(msg, 2)

        elif files_to_sync_count > 0:
            msg = "\n <span style='color:#2C93E2'>Syncing {} published files of entity children.... </span> \n".format(files_to_sync_count)
            self._add_log(msg, 2)
            self._do_sync_files_threading_thread_2(files_to_sync, entity=True)

            msg = "\n <span style='color:#2C93E2'>Syncing entity children published files is complete</span> \n"
            self._add_log(msg, 2)

    def _on_sync_entity_files(self):
        """
        Callback method when the sync entity files button is clicked
        """
        self._sync_entity_parents_published_files()
        self._sync_entity_children_published_files()

    def _load_publishes_for_parents_entity(self, sg_data):
        """
        Load the publishes for the parents of the selected entity
        :param sg_data: Shotgun data for the selected entity
        """
        child_folders = []
        # No need to show sub items if we are in the entity presets mode.
        show_sub_items = False
        self.ui.entity_parents_view.setStyleSheet("")
        self._entity_parents_thumb_delegate.set_sub_items_mode(False)
        self._entity_parents_list_delegate.set_sub_items_mode(False)

        # now finally load up the data in the entity_parents model
        publish_filters = self._entity_presets[
            self._current_entity_preset
        ].publish_filters
        self._entity_parents_model.load_data(
            sg_data, child_folders, show_sub_items, publish_filters
        )

    def _load_publishes_for_children_entity(self, sg_data):
        """
        Load the publishes for the children of the selected entity
        :param sg_data: Shotgun data for the selected entity
        """
        child_folders = []
        # No need to show sub items if we are in the entity presets mode.
        show_sub_items = False
        self.ui.entity_children_view.setStyleSheet("")
        self._entity_children_thumb_delegate.set_sub_items_mode(False)
        self._entity_children_list_delegate.set_sub_items_mode(False)

        # now finally load up the data in the entity_children model
        publish_filters = self._entity_presets[
            self._current_entity_preset
        ].publish_filters

        self._entity_children_model.load_data(
            sg_data, child_folders, show_sub_items, publish_filters
        )


    def _setup_file_details_panel(self, items):
        """
        Sets up the file details panel with info for a given item.
        """

        def __make_table_row(left, right):
            """
            Helper method to make a detail table row
            """
            return (
                "<tr><td><b style='color:#2C93E2'>%s</b>&nbsp;</td><td>%s</td></tr>"
                % (left, right)
            )

        def __set_publish_ui_visibility(is_publish):
            """
            Helper method to enable disable publish specific details UI
            """
            # disable version file_history stuff
            self.ui.version_file_history_label.setEnabled(is_publish)
            self.ui.file_history_view.setEnabled(is_publish)

            # hide actions and playback stuff
            self.ui.file_detail_actions_btn.setVisible(is_publish)
            self.ui.file_detail_playback_btn.setVisible(is_publish)


        def __clear_publish_file_history(pixmap):
            """
            Helper method that clears the file_history view on the right hand side.

            :param pixmap: image to set at the top of the file_history view.
            """
            self._publish_file_history_model.clear()
            self.ui.file_details_header.setText("")
            self.ui.file_details_image.setPixmap(pixmap)
            __set_publish_ui_visibility(False)

        # note - before the UI has been shown, querying isVisible on the actual
        # widget doesn't work here so use member variable to track state instead
        if not self._details_pane_visible:
            return

        if len(items) == 0:
            __clear_publish_file_history(self._no_selection_pixmap)
        elif len(items) > 1:
            __clear_publish_file_history(self._multiple_publishes_pixmap)
        else:

            model_index = items[0]
            # the incoming model index is an index into our proxy model
            # before continuing, translate it to an index into the
            # underlying model
            proxy_model = model_index.model()
            source_index = proxy_model.mapToSource(model_index)

            # now we have arrived at our model derived from StandardItemModel
            # so let's retrieve the standarditem object associated with the index
            item = source_index.model().itemFromIndex(source_index)
            published_file_type = None
            sg_data = item.get_sg_data()
            if sg_data:
                published_file_type = sg_data.get('type', None)
            if published_file_type and published_file_type not in ['PublishedFile']:
                __clear_publish_file_history(self._no_selection_pixmap)
                return
            """
            if sg_data:
                # published_file_type = sg_data.get('published_file_type', None)
                published_file_type = sg_data.get('type', None)
                logger.debug(">>>>> Type is {}".format(sg_data.get('type', None)))
                if published_file_type not in ['PublishedFile']:
                # if not published_file_type:
                    __clear_publish_file_history(self._no_selection_pixmap)
                    return
            """
            # render out file_details
            thumb_pixmap = item.icon().pixmap(512)
            self.ui.file_details_image.setPixmap(thumb_pixmap)

            if sg_data is None:
                # an item which doesn't have any sg data directly associated
                # typically an item higher up the tree
                # just use the default text
                folder_name = __make_table_row("Name", item.text())
                self.ui.file_details_header.setText("<table>%s</table>" % folder_name)
                __set_publish_ui_visibility(False)

            elif item.data(SgLatestPublishModel.IS_FOLDER_ROLE):
                # folder with sg data - basically a leaf node in the entity tree

                status_code = sg_data.get("sg_status_list")
                if status_code is None:
                    status_name = "No Status"
                else:
                    status_name = self._status_model.get_long_name(status_code)

                status_color = self._status_model.get_color_str(status_code)
                if status_color:
                    status_name = (
                        "%s&nbsp;<span style='color: rgb(%s)'>&#9608;</span>"
                        % (status_name, status_color)
                    )

                if sg_data.get("description"):
                    desc_str = sg_data.get("description")
                else:
                    desc_str = "No description entered."

                msg = ""
                display_name = shotgun_globals.get_type_display_name(sg_data["type"])
                msg += __make_table_row(
                    "Name", "%s %s" % (display_name, sg_data.get("code"))
                )
                msg += __make_table_row("Status", status_name)
                msg += __make_table_row("Description", desc_str)
                self.ui.file_details_header.setText("<table>%s</table>" % msg)

                # blank out the version file_history
                __set_publish_ui_visibility(False)
                self._publish_file_history_model.clear()

            else:
                # this is a publish!
                __set_publish_ui_visibility(True)

                sg_item = item.get_sg_data()

                # sort out the actions button
                actions = self._action_manager.get_actions_for_publish(
                    sg_item, self._action_manager.UI_AREA_DETAILS
                )
                if len(actions) == 0:
                    self.ui.file_detail_actions_btn.setVisible(False)
                else:
                    self.ui.file_detail_playback_btn.setVisible(True)
                    self._file_details_action_menu.clear()
                    for a in actions:
                        self._dynamic_widgets.append(a)
                        self._file_details_action_menu.addAction(a)

                # if there is an associated version, show the play button
                if sg_item.get("version"):
                    sg_url = sgtk.platform.current_bundle().shotgun.base_url
                    url = "%s/page/media_center?type=Version&id=%d" % (
                        sg_url,
                        sg_item["version"]["id"],
                    )

                    self.ui.file_detail_playback_btn.setVisible(True)
                    self._current_version_detail_playback_url = url
                else:
                    self.ui.file_detail_playback_btn.setVisible(False)
                    self._current_version_detail_playback_url = None

                if sg_item.get("name") is None:
                    name_str = "No Name"
                else:
                    name_str = sg_item.get("name")

                type_str = shotgun_model.get_sanitized_data(
                    item, SgLatestPublishModel.PUBLISH_TYPE_NAME_ROLE
                )

                msg = ""
                msg += __make_table_row("Name", name_str)
                msg += __make_table_row("Type", type_str)

                version = sg_item.get("version_number")
                vers_str = "%03d" % version if version is not None else "N/A"

                msg += __make_table_row("Version", "%s" % vers_str)

                if sg_item.get("entity"):
                    display_name = shotgun_globals.get_type_display_name(
                        sg_item.get("entity").get("type")
                    )
                    entity_str = "<b>%s</b> %s" % (
                        display_name,
                        sg_item.get("entity").get("name"),
                    )
                    msg += __make_table_row("Link", entity_str)

                # sort out the task label
                if sg_item.get("task"):

                    if sg_item.get("task.Task.content") is None:
                        task_name_str = "Unnamed"
                    else:
                        task_name_str = sg_item.get("task.Task.content")

                    if sg_item.get("task.Task.sg_status_list") is None:
                        task_status_str = "No Status"
                    else:
                        task_status_code = sg_item.get("task.Task.sg_status_list")
                        task_status_str = self._status_model.get_long_name(
                            task_status_code
                        )

                    msg += __make_table_row(
                        "Task", "%s (%s)" % (task_name_str, task_status_str)
                    )

                # if there is a version associated, get the status for this
                if sg_item.get("version.Version.sg_status_list"):
                    task_status_code = sg_item.get("version.Version.sg_status_list")
                    task_status_str = self._status_model.get_long_name(task_status_code)
                    msg += __make_table_row("Review", task_status_str)

                if sg_item.get("revision"):
                    revision = sg_item.get("revision")
                    msg += __make_table_row("Revision#", revision)


                if sg_item.get("action"):
                    action = sg_item.get("action")
                    msg += __make_table_row("Action", action)
                else:
                    if sg_item.get("headAction"):
                        head_action = sg_item.get("headAction", "N/A")
                        msg += __make_table_row("Action", head_action)


                self.ui.file_details_header.setText("<table>%s</table>" % msg)

                # tell details pane to load stuff
                sg_data = item.get_sg_data()
                self._publish_file_history_model.load_data(sg_data)

            self.ui.file_details_header.updateGeometry()

    def _on_detail_version_playback(self):
        """
        Callback when someone clicks the version playback button
        """
        # the code that sets up the version button also populates
        # a member variable which olds the current media center url.
        if self._current_version_detail_playback_url:
            QDesktopServices.openUrl(
                QUrl(self._current_version_detail_playback_url)
            )

    ########################################################################################
    # file_history related

    def _compute_file_history_button_visibility(self):
        """
        compute file_history button enabled/disabled state based on contents of file_history stack.
        """
        self.ui.navigation_next.setEnabled(True)
        self.ui.navigation_prev.setEnabled(True)
        if self._file_history_index == len(self._file_history):
            self.ui.navigation_next.setEnabled(False)
        if self._file_history_index == 1:
            self.ui.navigation_prev.setEnabled(False)

    def _add_file_history_record(self, preset_caption, std_item):
        """
        Adds a record to the file_history stack
        """
        # self._file_history_index is a one based index that points at the currently displayed
        # item. If it is not pointing at the last element, it means a user has stepped back
        # in that case, discard the file_history after the current item and add this new record
        # after the current item

        if (
            not self._file_history_navigation_mode
        ):  # do not add to file_history when browsing the file_history :)
            # chop off file_history at the point we are currently
            self._file_history = self._file_history[: self._file_history_index]
            # append our current item to the chopped file_history
            self._file_history.append({"preset": preset_caption, "item": std_item})
            self._file_history_index += 1

        # now compute buttons
        self._compute_file_history_button_visibility()

    def _file_history_navigate_to_item(self, preset, item):
        """
        Focus in on an item in the tree view.
        """
        # tell rest of event handlers etc that this navigation
        # is part of a file_history click. This will ensure that no
        # *new* entries are added to the file_history log when we
        # are clicking back/next...
        self._file_history_navigation_mode = True
        try:
            self._select_item_in_entity_tree(preset, item)
        finally:
            self._file_history_navigation_mode = False

    def _on_home_clicked(self):
        """
        User clicks the home button.
        """
        # first, try to find the "home" item by looking at the current app context.
        found_preset = None
        found_hierarchy_preset = None
        found_item = None

        # get entity portion of context
        ctx = sgtk.platform.current_bundle().context

        if ctx.entity:
            # now step through the profiles and find a matching entity
            for preset_index, preset in self._entity_presets.items():

                if isinstance(preset.model, SgHierarchyModel):
                    # Found a hierarchy model, we select it right away, since it contains the
                    # entire project, no need to scan for other tabs.
                    found_hierarchy_preset = preset_index
                    break
                else:
                    if preset.entity_type == ctx.entity["type"]:
                        # found an at least partially matching entity profile.
                        found_preset = preset_index

                        # now see if our context object also exists in the tree of this profile
                        model = preset.model
                        item = model.item_from_entity(
                            ctx.entity["type"], ctx.entity["id"]
                        )

                        if item is not None:
                            # find an absolute match! Break the search.
                            found_item = item
                            break

        if found_hierarchy_preset:
            # We're about to programmatically set the tab and then the item, so inform
            # the tab switcher that this is a combo operation and shouldn't be tracked
            # by the file_history.
            self._select_tab(found_hierarchy_preset, track_in_file_history=False)
            # Kick off an async load of an entity, which in the context of the loader
            # is always meant to switch select that item.
            preset.model.async_item_from_entity(ctx.entity)
            return
        else:
            if found_preset is None:
                # no suitable item found. Use the first tab
                found_preset = self.ui.entity_preset_tabs.tabText(0)

            # select it in the left hand side tree view
            self._select_item_in_entity_tree(found_preset, found_item)

    def _on_back_clicked(self):
        """
        User clicks the back button
        """
        self._file_history_index += -1
        # get the data for this guy (note: index are one based)
        d = self._file_history[self._file_history_index - 1]
        self._file_history_navigate_to_item(d["preset"], d["item"])
        self._compute_file_history_button_visibility()

    def _on_forward_clicked(self):
        """
        User clicks the forward button
        """
        self._file_history_index += 1
        # get the data for this guy (note: index are one based)
        d = self._file_history[self._file_history_index - 1]
        self._file_history_navigate_to_item(d["preset"], d["item"])
        self._compute_file_history_button_visibility()

    ########################################################################################
    # filter view

    def _apply_type_filters_on_publishes(self):
        """
        Executed when the type listing changes
        """
        # go through and figure out which checkboxes are clicked and then
        # update the publish proxy model so that only items of that type
        # is displayed
        sg_type_ids = self._publish_type_model.get_selected_types()
        show_folders = self._publish_type_model.get_show_folders()
        self._publish_proxy_model.set_filter_by_type_ids(sg_type_ids, show_folders)

    ########################################################################################
    # publish view

    def _on_publish_content_change(self):
        """
        Triggered when the number of columns in the model is changing
        """
        # if no publish items are visible, display not found overlay
        num_pub_items = self._publish_proxy_model.rowCount()

        if num_pub_items == 0:
            # show 'nothing found' image
            self._publish_main_overlay.show_message_pixmap(self._no_pubs_found_icon)
        else:
            self._publish_main_overlay.hide()



    def _on_show_subitems_toggled(self):
        """
        Triggered when the show sub items checkbox is clicked
        """

        # Check if we should pop up that help screen.
        # The hierarchy model cannot handle "Show items in subfolders" mode.
        if self.ui.show_sub_items.isChecked() and not isinstance(
            self._entity_presets[self._current_entity_preset].model, SgHierarchyModel
        ):
            subitems_shown = self._settings_manager.retrieve(
                "subitems_shown", False, self._settings_manager.SCOPE_ENGINE
            )
            if subitems_shown == False:
                # store in settings that we now clicked the subitems at least once
                self._settings_manager.store(
                    "subitems_shown", True, self._settings_manager.SCOPE_ENGINE
                )
                # and display help
                app = sgtk.platform.current_bundle()
                help_pix = [
                    QPixmap(":/res/subitems_help_1.png"),
                    QPixmap(":/res/subitems_help_2.png"),
                    QPixmap(":/res/subitems_help_3.png"),
                    QPixmap(":/res/help_4.png"),
                ]
                help_screen.show_help_screen(self.window(), app, help_pix)

        # tell publish UI to update itself
        item = self._get_selected_entity()
        self._load_publishes_for_entity_item(item)
        # self._get_perforce_summary()

    def _on_thumb_size_slider_change(self, value):
        """
        When scale slider is manipulated
        """
        self.ui.publish_view.setIconSize(QSize(value, value))
        self._settings_manager.store("thumb_size_scale", value)

    def _on_publish_selection(self, selected, deselected):
        """
        Slot triggered when someone changes the selection in the main publish area
        """
        selected_indexes = self.ui.publish_view.selectionModel().selectedIndexes()
        #logger.debug(">>>>>>>>>>> selected_indexes:{}".format(selected_indexes))
        if len(selected_indexes) == 0:
            self._setup_file_details_panel([])
        else:
            self._setup_file_details_panel(selected_indexes)

        # emit the selection changed signal:
        self.selection_changed.emit()

    def _on_publish_double_clicked(self, model_index):
        """
        When someone double clicks on a publish, run the default action
        """
        # the incoming model index is an index into our proxy model
        # before continuing, translate it to an index into the
        # underlying model
        proxy_model = model_index.model()
        source_index = proxy_model.mapToSource(model_index)

        # now we have arrived at our model derived from StandardItemModel
        # so let's retrieve the standarditem object associated with the index
        item = source_index.model().itemFromIndex(source_index)

        is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)

        if is_folder:
            # get the corresponding tree view item
            tree_view_item = self._publish_model.get_associated_tree_view_item(item)

            # select it in the tree view
            self._select_item_in_entity_tree(
                self._current_entity_preset, tree_view_item
            )

        else:
            # Run default action.
            sg_item = shotgun_model.get_sg_data(model_index)
            published_type = sg_item.get("type", None)
            # Todo: Check if there are other types that need to be handled
            if published_type in ["PublishedFile"]:
                default_action = self._action_manager.get_default_action_for_publish(
                    sg_item, self._action_manager.UI_AREA_MAIN
                )
                if default_action:
                    default_action.trigger()

    def get_p4(self):
        return self._p4

    def _clear_pending_view_widget(self):
        """
        Clears the pending view widget to reset its state.
        """
        if self.submitter_widget:
            self.submitter_widget.clearSelection()
            self.submitter_widget.setModel(None)


    def _on_submit_files(self):
        """
        When someone clicks on the "Submit Files" button
        Show the SubmitChangelist Widget
        """
        # Clear the pending view widget before using it again
        #self._clear_pending_view_widget()
        self.change_sg_item = self._get_submit_changelist_widget_data()
        if self.change_sg_item and self._submit_widget_dict:
            self.submitter_widget = SubmitChangelistWidget(parent=self, myp4=self._p4, change_item=self.change_sg_item, file_dict=self._submit_widget_dict)
            #logger.debug(">>>>>>>>>>> Submit Widget Dict:{}".format(self._submit_widget_dict))

            self.submitter_widget.show()
        else:
            msg = "\n <span style='color:#2C93E2'>No files selected for submission.</span> \n"
            self._add_log(msg, 2)

    def _get_submit_changelist_widget_data(self):
        """
        When someone clicks on the "Submit Files" button
        Show the SubmitChangelist Widget
        """
        selected_indexes = self._pending_view_widget.selectionModel().selectedRows()
        selected_depot_files = []
        self._submit_widget_dict = {}
        change_sg_item = None

        for selected_index in selected_indexes:
            try:
                source_index = self._pending_view_model.mapToSource(selected_index)
                change = self._get_change_data_from_source(source_index)
                # logger.debug("-----------------------------------------------")
                # logger.debug(">>>>>>>>>>> change:{}".format(change))
                change_key = str(change)
                children = self._change_dict.get(change_key, None)
                #logger.debug(">>>>>>>>>>>change dict:")
                #for k, v in self._change_dict.items():
                #    logger.debug("Change:{} values:{}".format(k, v))

                if children:
                    for sg_item in children:
                        # logger.debug(">>>>>>>>>>> sg_item:{}".format(sg_item))
                        if sg_item:
                            if 'depotFile' in sg_item:
                                depot_file = sg_item.get('depotFile', None)
                                if depot_file and depot_file not in selected_depot_files:
                                    selected_depot_files.append(depot_file)
                                    file_info = {}
                                    file_name, folder, file_type = self._extract_file_info(depot_file)
                                    action = self._get_action(sg_item)
                                    file_info["file"] = file_name
                                    file_info["folder"] = folder
                                    file_info["type"] = file_type
                                    file_info["sg_item"] = sg_item
                                    file_info["pending_action"] = action
                                    file_info["resolve_status"] = "N/A"
                                    key = (file_name, folder)
                                    self._submit_widget_dict[key] = file_info
                            if 'changeListInfo' in sg_item:
                                change_sg_item = sg_item
                                change_sg_item["change"] = change

            except Exception as e:
                logger.debug("Error getting file info: {}".format(e))

        return change_sg_item

    def _extract_file_info(self, target_file):
        # Get file name, extension and folder
        file_name = os.path.basename(target_file)
        folder = os.path.dirname(target_file)
        extension = os.path.splitext(file_name)[1]
        extension = extension[1:] if extension else "N/A"
        # logger.debug(">>>>>>>>>>> Extension:{}".format(extension))
        type = self.settings.get(extension, "N/A")
        # logger.debug(">>>>>>>>>>> Type:{}".format(type))
        return file_name, folder, type

    def _on_submit_changelist(self, submitter_widget):
        """
        Callback for the submit button in the SubmitChangelistWidget
        """
        description = submitter_widget.changelist_description.toPlainText()
        selected_files = []
        for row in range(submitter_widget.files_table_widget.rowCount()):
            if submitter_widget.files_table_widget.item(row, 0).checkState() == Qt.Checked:
                file_info = {
                    "file": submitter_widget.files_table_widget.item(row, 1).text(),
                    "folder": submitter_widget.files_table_widget.item(row, 2).text(),
                    "resolve_status": submitter_widget.files_table_widget.item(row, 3).text(),
                    "type": submitter_widget.files_table_widget.item(row, 4).text(),
                    "pending_action": submitter_widget.files_table_widget.item(row, 5).text(),
                }
                selected_files.append(file_info)

        if not description:
            QMessageBox.warning(submitter_widget, "Warning", "Changelist description cannot be empty.")
            return

        if not selected_files:
            QMessageBox.warning(submitter_widget, "Warning", "No files selected for submission.")
            return

        # Here you would add the logic to submit the changelist with the selected files and description
        print(f"Submitting changelist with description: {description}")
        print("Files to be submitted:")
        for file_info in selected_files:
            print(f"- {file_info}")

        # Close the dialog after submission
        submitter_widget.accept()

    def _on_submit_files_original(self):
        """
                When someone clicks on the "Submit Files" button
        """
        self.on_submit_deleted_files()
        self.on_submit_other_files()
        msg = "\n <span style='color:#2C93E2'>Updating the Pending view ...</span> \n"
        self._add_log(msg, 2)
        # Update the Pending view
        self.update_pending_view()
        #logger.debug(">>>>>>>>>>> Updating the publish view as well")
        self._on_treeview_item_selected()

    def on_submit_deleted_files(self, change_sg_item, file_info_deleted):
        """
        When someone clicks on the "Submit Files" button
        Send pending files to the Shotgrid Publisher.
        """
        selected_files_to_delete = []
        selected_tuples_to_delete = []
        selected_tuples_to_publish = []
        change = change_sg_item.get("change", None)
        # logger.debug(">>>>>>> on_submit_deleted_files: change:{}".format(change))
        for file_info in file_info_deleted:
            target_file = None
            try:
                action = file_info.get("pending_action", None)
                # logger.debug(">>>>>>> on_submit_deleted_files: action:{}".format(action))

                sg_item = file_info.get("sg_item", None)
                # logger.debug(">>>>>>> on_submit_deleted_files: sg_item:{}".format(sg_item))
                if sg_item:
                    target_file = sg_item.get("depotFile", None)
                    # logger.debug(">>>>>>> on_submit_deleted_files: target_file:{}".format(target_file))

                    if action in ["delete"]:
                        if target_file not in selected_files_to_delete:
                            delete_tuple = (change, target_file)
                            publish_tuple = (change, target_file, action, sg_item)
                            selected_files_to_delete.append(target_file)
                            selected_tuples_to_delete.append(delete_tuple)
                            selected_tuples_to_publish.append(publish_tuple)

            except Exception as e:
                logger.debug("Error deleting file {}: {}".format(target_file, e))

        if selected_files_to_delete:
            # logger.debug("_on_submit_deleted_files: selected_files_to_delete: {}".format(selected_files_to_delete))

            # Convert list of files into a string, to show in the confirmation dialog
            files_str = "\n".join(selected_files_to_delete)

            # Show confirmation dialog
            reply = QMessageBox.question(self, 'Confirmation',
                                         f"Are you sure you want to delete the following files in Perforce?\n\n{files_str}",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

            if reply == QMessageBox.Yes:
                msg = "\n <span style='color:#2C93E2'>Submitting pending files for deletion in Perforce...</span> \n"
                self._add_log(msg, 2)
                if selected_files_to_delete:
                    self._publish_pending_data_using_command_line(selected_tuples_to_publish)
                    self._delete_pending_data(selected_tuples_to_delete)

                msg = "\n <span style='color:#2C93E2'>Updating the Pending view ...</span> \n"
                self._add_log(msg, 2)
                # Update the Pending view
                # self.update_pending_view()
        else:
            msg = "\n <span style='color:#2C93E2'>Please select files marked for deletion in the Pending view...</span> \n"
            self._add_log(msg, 2)

    def on_submit_other_files(self, change_sg_item, file_info_other):
        """
        When someone clicks on the "Submit Files" button
        Send pending files to the Shotgrid Publisher.
        """
        selected_files_to_submit = []
        selected_tuples_to_submit = []
        change = change_sg_item.get("change", None)
        for file_info in file_info_other:
            try:
                target_file = None
                action = file_info.get("pending_action", None)
                sg_item = file_info.get("sg_item", None)
                if sg_item:
                    target_file = sg_item.get("depotFile", None)

                    if target_file and action not in ["delete"]:
                        if target_file not in selected_files_to_submit:
                            submit_tuple = (change, target_file, action, sg_item)
                            selected_files_to_submit.append(target_file)
                            selected_tuples_to_submit.append(submit_tuple)

            except Exception as e:
                logger.debug("{}".format(e))

        if selected_files_to_submit:

            self._submit_other_pending_data(selected_tuples_to_submit)
            self._publish_pending_data_using_command_line(selected_tuples_to_submit)


    def _publish_file_thread(self, change, target_file, action, sg_item, log_callback, get_entity_callback):
        """
        Function to publish a file in a separate thread.
        """
        try:
            description = sg_item.get("description", None)
            entity, new_sg_item = get_entity_callback(sg_item)

            if entity:
                if new_sg_item:
                    sg_item.update(new_sg_item)
                    sg_item["description"] = description
                else:
                    sg_item["entity"] = entity

                if 'path' in sg_item:
                    rev = sg_item.get("version_number") or sg_item.get("headRev") or 1
                    file_to_publish = sg_item['path'].get('local_path', None)
                    log_callback(f"Publishing file: {file_to_publish}#{rev}", 4)

                    publisher = PublishItem(sg_item)
                    publish_result = publisher.commandline_publishing()

                    if publish_result:
                        log_callback(f"New data is: {publish_result}", 4)
            else:
                log_callback(f"Unable to find the entity associated with the file: {target_file}", 4)

        except Exception as e:
            log_callback(f"Error publishing file {target_file}: {str(e)}", 4)

    def _publish_pending_data_using_command_line(self, selected_tuples_to_publish):
        """
        Publish Depot Data using threading for speedup.
        """
        logger.debug(">>>>>>>>>>>  _publish_pending_data_using_command_line")
        logger.debug(">>>>>>>>>>>  selected_tuples_to_publish:{}".format(selected_tuples_to_publish))
        if selected_tuples_to_publish:
            msg = "\n <span style='color:#2C93E2'>Publishing pending files in Shotgrid</span> \n"
            self._add_log(msg, 2)

            # List to store active threads
            threads = []

            # Create a thread for each file to publish
            for change, target_file, action, sg_item in selected_tuples_to_publish:
                thread = threading.Thread(target=self._publish_file_thread,
                                          args=(change, target_file, action, sg_item, self._add_log,
                                                self.get_entity_from_sg_item))
                threads.append(thread)
                thread.start()

            # Wait for all threads to finish
            for thread in threads:
                thread.join()

            msg = "\n <span style='color:#2C93E2'>Publishing files is complete</span> \n"
            self._add_log(msg, 2)
        else:
            msg = "\n <span style='color:#2C93E2'>No need to publish any file</span> \n"
            self._add_log(msg, 2)

    def get_entity_from_sg_item(self, sg_item):
        # Check if the filepath leads to a valid shotgrid entity
        entity, published_file = check_validity_by_published_file(sg_item)
        if not entity:
            entity, published_file = check_validity_by_path_parts(swc_fw, sg_item)
        return entity, published_file


    def convert_to_relative_path(self, absolute_path):
        # Split the path on ":/" and take the second part, if it exists
        parts = absolute_path.split(":/", 1)
        relative_path = parts[1] if len(parts) > 1 else absolute_path

        return relative_path

    def _on_submit_other_files_original(self):
        """
        When someone clicks on the "Submit Files" button
        Send pending files to the Shotgrid Publisher.
        """
        # Publish depot files
        # Get the selected pending files
        other_data_to_publish, deleted_data_to_publish = self.pending_tree_view.get_selected_publish_items_by_action()
        #logger.debug(">>>>>>>>>>  other_data_to_publish: {}".format(other_data_to_publish))
        #logger.debug(">>>>>>>>>>  deleted_data_to_publish: {}".format(deleted_data_to_publish))
        if other_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Submitting other pending files...</span> \n"
            self._add_log(msg, 2)
            if other_data_to_publish:
                pass
                # self._publish_other_pending_data(other_data_to_publish)
                #logger.debug(">>>>>>>>>>  other_data_to_publish: {}".format(other_data_to_publish))

            msg = "\n <span style='color:#2C93E2'>Updating the Pending view ...</span> \n"
            self._add_log(msg, 2)
            # Update the Pending view
            self.update_pending_view()
        else:
            msg = "\n <span style='color:#2C93E2'>Please select files in the Pending view...</span> \n"
            self._add_log(msg, 2)



    def _delete_pending_data_original(self, selected_tuples_to_delete):
        """
        Publish Depot Data in the Pending view that needs to be deleted.
        """
        if selected_tuples_to_delete:
            msg = "\n <span style='color:#2C93E2'>Submitting files for deletion...</span> \n"
            self._add_log(msg, 2)
            for change, file_to_submit in selected_tuples_to_delete:

                #logger.debug(">>>>>>>>>>  file_to_submit: {}".format(file_to_submit))
                #logger.debug(">>>>>>>>>>  change: {}".format(change))
                if change and file_to_submit:
                    try:
                        msg = "{}".format(file_to_submit)
                        self._add_log(msg, 4)
                        submit_result, perforce_msg = submit_and_delete_file(self._p4, change, file_to_submit)
                        msg = "Result of submitting file: {}".format(submit_result)
                        self._add_log(msg, 4)
                        #if perforce_msg:
                        #    # Log the error message
                        #    msg = "\n <span style='color:#CC3333'>{}</span> \n".format(perforce_msg)
                        #    self._add_log(msg, 4)
                        if submit_result and not perforce_msg:
                            msg = "\n <span style='color:#2C93E2'>File deleted from Perforce:</span> \n".format(file_to_submit)
                            self._add_log(msg, 2)
                    except Exception as e:
                        logger.debug("Error deleting file {}: {}".format(file_to_submit, e))

    def _delete_file_thread(self, p4, change, file_to_submit, log_callback):
        """
        Function to delete a file in a separate thread.
        """
        try:
            submit_result, perforce_msg = submit_and_delete_file(p4, change, file_to_submit)
            if submit_result and not perforce_msg:
                log_callback(f"File deleted from Perforce: {file_to_submit}", 2)
            else:
                log_callback(f"Error deleting file {file_to_submit}: {perforce_msg}", 4)
        except Exception as e:
            log_callback(f"Error deleting file {file_to_submit}: {str(e)}", 4)

    def _delete_pending_data(self, selected_tuples_to_delete):
        """
        Delete Depot Data in the Pending view that needs to be deleted.
        """
        if selected_tuples_to_delete:
            msg = "\n <span style='color:#2C93E2'>Submitting files for deletion...</span> \n"
            self._add_log(msg, 2)

            # List to store active threads
            threads = []

            # Create a thread for each file to delete
            for change, file_to_submit in selected_tuples_to_delete:
                # Create a thread for each deletion
                thread = threading.Thread(target=self._delete_file_thread,
                                          args=(self._p4, change, file_to_submit, self._add_log))
                threads.append(thread)
                thread.start()

            # Wait for all threads to finish
            for thread in threads:
                thread.join()

            msg = "\n <span style='color:#2C93E2'>File deletion completed.</span> \n"
            self._add_log(msg, 2)

    def _submit_other_pending_data(self, selected_data_to_submit):
        """
        Publish Depot Data in the Pending view that are not marked for deletion.
        """
        if selected_data_to_submit:
            msg = "\n <span style='color:#2C93E2'>Submitting other pending files...</span> \n"
            self._add_log(msg, 2)

            for change, file_to_submit, action, sg_item in selected_data_to_submit:
                # logger.debug(">>>>>>>>>>  file_to_submit: {}".format(file_to_submit))
                # logger.debug(">>>>>>>>>>  change: {}".format(change))
                if change and file_to_submit and action:
                    if action not in ["delete"]:
                        msg = "{}".format(file_to_submit)
                        self._add_log(msg, 4)
                        submit_res = submit_single_file(self._p4, change, file_to_submit, action)
                        logger.debug("Result of submitting files: {}".format(submit_res))
                        if submit_res:
                            msg = "\n <span style='color:#2C93E2'>File submitted to Perforce:</span> \n".format(file_to_submit)
                            self._add_log(msg, 2)


    def _publish_other_pending_data(self, other_data_to_publish):
        """
        Publish Depot Data in the Pending view that does not need to be deleted.
        """

        if other_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Submitting pending files that are not marked for delete...</span> \n"
            self._add_log(msg, 2)
            # Create publish file
            out_file = open(self._publish_files_path, 'w')
            out_file.write('Pending Files\n')
            # Create a new Perforce changelist

            for key in other_data_to_publish:
                for sg_item in other_data_to_publish[key]:
                    # logger.debug(">>>>>>>>>>  sg_item: {}".format(sg_item))
                    if sg_item and 'path' in sg_item:
                        file_to_submit = sg_item['path'].get('local_path', None)
                        if file_to_submit:
                            msg = "{}".format(file_to_submit)
                            self._add_log(msg, 4)
                            out_file.write('%s\n' % file_to_submit)
                            #add_res = add_to_change(self._p4, change, file_to_submit)
                            #action_result = self._p4.run("edit", "-c", change, "-v", file_to_submit)

            out_file.close()

            # Run the publisher UI
            msg = "\n <span style='color:#2C93E2'>Initializing Publisher UI, please stand by...</span> \n"
            self._add_log(msg, 2)

            engine = sgtk.platform.current_engine()
            engine.commands["Publish..."]["callback"]()

            # Update the Pending view

            msg = "\n <span style='color:#2C93E2'>Updating the Pending View ...</span> \n"
            self._add_log(msg, 2)
            self.update_pending_view()


    def _publish_delete_pending_data(self, deleted_data_to_publish):
        """
        Publish Depot Data in the Pending view that needs to be deleted.
        """
        files_to_delete = []
        if deleted_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Submitting files for deletion...</span> \n"
            self._add_log(msg, 2)
            for key in deleted_data_to_publish:

                for sg_item in deleted_data_to_publish[key]:
                    # logger.debug(">>>>>>>>>>  sg_item: {}".format(sg_item))

                    file_to_submit = sg_item.get('path', {}).get('local_path', None) if 'path' in sg_item else None

                    if file_to_submit:
                        msg = "{}".format(file_to_submit)
                        self._add_log(msg, 4)
                        submit_del_res = submit_change(self._p4, file_to_submit)
                        logger.debug("Result of deleting files: {}".format(submit_del_res))
                        if submit_del_res:
                            # Check if submit_del_res is a list
                            if isinstance(submit_del_res, list) and len(submit_del_res) > 0:
                                submit_del_res = submit_del_res[0]
                                if 'submittedChange' in submit_del_res:
                                    sg_item['submittedChange'] = submit_del_res['submittedChange']
                                    self._publish_deleted_data_using_command_line([sg_item])

            self._publish_deleted_data_using_command_line(deleted_data_to_publish)

    def _publish_deleted_data_using_command_line_original(self, deleted_data_to_publish):
        """
        Publish Pending view Depot Data that needs to be deleted using the command line.
        """
        if deleted_data_to_publish:
            for sg_item in deleted_data_to_publish:
                #logger.debug(">>>>>>>>>>  sg_item {}".format(sg_item))
                file_path = sg_item['path'].get('local_path', None) if 'path' in sg_item else None
                #logger.debug(">>>>>>>>>>  file_path {}".format(file_path))
                target_context = self._find_task_context(file_path)
                #logger.debug(">>>>>>>>>>  target_context.entity {}".format(target_context.entity))
                if target_context.entity and file_path:
                    sg_item["entity"] = target_context.entity

                    # Publish the file to Shotgrid with a new version number and "delete" action

                    publisher = PublishItem(sg_item)
                    publish_result = publisher.commandline_publishing()
                    if publish_result:
                        logger.debug("New data is: {}".format(publish_result))

            msg = "\n <span style='color:#2C93E2'>Publishing files marked for delete is complete</span> \n"
            self._add_log(msg, 2)
        else:
            msg = "\n <span style='color:#2C93E2'>No need to publish any file that is marked for deletion</span> \n"
            self._add_log(msg, 2)


    def _publish_deleted_data_using_command_line(self, deleted_data_to_publish):
        """
        Publish Pending view Depot Data that needs to be deleted using the command line, with threading for speedup.
        """
        if deleted_data_to_publish:
            # List to store active threads
            threads = []

            for sg_item in deleted_data_to_publish:
                file_path = sg_item['path'].get('local_path', None) if 'path' in sg_item else None
                target_context = self._find_task_context(file_path)

                if target_context.entity and file_path:
                    sg_item["entity"] = target_context.entity

                    # Create a thread for each delete task
                    thread = threading.Thread(target=self._delete_one_file_thread,
                                              args=(sg_item, file_path))
                    threads.append(thread)
                    thread.start()

            # Wait for all threads to finish
            for thread in threads:
                thread.join()

            msg = "\n <span style='color:#2C93E2'>Publishing files marked for delete is complete</span> \n"
            self._add_log(msg, 2)
        else:
            msg = "\n <span style='color:#2C93E2'>No need to publish any file that is marked for deletion</span> \n"
            self._add_log(msg, 2)

    def _delete_one_file_thread(self, sg_item, file_path):
        """
        Delete a single file in a thread.
        """
        # Publish the file to Shotgrid with a new version number and "delete" action
        publisher = PublishItem(sg_item)
        publish_result = publisher.commandline_publishing()
        if publish_result:
            logger.debug("New data is: {}".format(publish_result))

    def _get_published_files(self, sg_item):

        # Define the file path of the published file
        file_path = sg_item['path'].get('local_path', None) if 'path' in sg_item else None

        # Construct the Shotgrid API query filters
        filters = [
            ["path", "contains", file_path],
            ["entity.Asset.sg_asset_type", "is_not", "Shot"],  # Optional filter to exclude shots
        ]

        # Specify the fields to retrieve for the versions
        fields = ["id", "code", "created_at", "user", "action", "step"]

        # Make the Shotgrid API call to search for versions
        versions = self._app.shotgun("Version", filters, fields, order=[{"field_name": "created_at", "direction": "asc"}])

        logger.debug("versions {}".format(versions))

    def _on_fix_list(self):
        # self._submitted_data_to_publish = []
        # logger.debug(">>>>>>>>>>   self._submitted_data_to_publish {}".format( self._submitted_data_to_publish))
        self._publish_submitted_data_using_command_line()

        self._setup_file_details_panel([])
        self._on_treeview_item_selected()

    def _on_fix_selected(self):
        """
        When someone clicks on the "Fix Selected" button
        Send unpublished depot files in the submitted view to the Shotgrid Publisher.
        """
        # Publish depot files
        #self._get_submitted_publish_data()

        self._submitted_data_to_publish = self.submitted_tree_view.get_selected_publish_items()
        #logger.debug(">>>>>>>>>>   self._submitted_data_to_publish {}".format( self._submitted_data_to_publish))
        #self._publish_submitted_data_using_publisher_ui()
        self._publish_submitted_data_using_command_line()

        self._setup_file_details_panel([])
        self._on_treeview_item_selected()
        
    def _on_fix_all(self):
        """
        When someone clicks on the "Fix All" button
        Send unpublished depot files in the submitted view to the Shotgrid Publisher.
        """
        self._submitted_data_to_publish = []
        for key in self._fstat_dict:
            # Find if it is published
            sg_item = self._fstat_dict[key]
            is_published = sg_item.get("Published", False)
            if not is_published:
                self._submitted_data_to_publish.append(sg_item)
        #logger.debug(">>>>>>>>>>   self._submitted_data_to_publish {}".format( self._submitted_data_to_publish))
        #self._publish_submitted_data_using_publisher_ui()
        self._publish_submitted_data_using_command_line()

        self._setup_file_details_panel([])
        self._on_treeview_item_selected()


    def _create_publisher_dir(self):
        home_dir = expanduser("~")
        self._home_dir = "{}/.publisher".format(home_dir)
        if not os.path.exists(self._home_dir):
            os.makedirs(self._home_dir)
        self._publish_files_path = "{}/publish_files.txt".format(self._home_dir)
        #logger.debug(">>>>>>>>>>   self._publish_files_path {}".format(self._publish_files_path))
        self._publish_files_description = "{}/publish_files_description.txt".format(self._home_dir)
        self._publisher_is_closed_path = "{}/publisher_is_closed.txt".format(self._home_dir)

    def _on_publish_files(self):
        files_count = len(self._action_data_to_publish)
        if files_count > 0:
            msg = "\n <span style='color:#2C93E2'>Publishing files ...</span> \n"
            self._add_log(msg, 2)

            for i, sg_item in enumerate(self._action_data_to_publish):
                if "local_path" in sg_item["path"]:
                    file_path = sg_item["path"].get("local_path", None)
                    if file_path:
                        rev = sg_item.get("version_number") or sg_item.get("headRev") or 1

                        msg = "({}/{})  Publishing file: {}#{}".format(i + 1, files_count, file_path, rev)
                        self._add_log(msg, 3)
                        publisher = PublishItem(sg_item)
                        publish_result = publisher.commandline_publishing()
        else:
            msg = "\n <span style='color:#2C93E2'>There are no files to publish</span> \n"
            self._add_log(msg, 2)

        # publisher = PublishManager()
        #publisher = P4SGPUBLISHER()
        #publisher = MultiPublish2()

        #engine = sgtk.platform.current_engine()
        #engine.commands['Publish...']["callback"]()

        # Reset _action_data_to_publish list
        self._action_data_to_publish = []


    def _on_sync_files(self):
        """
        When someone clicks on the "Sync Files" button
        """
        self._sync_current_file()
        # self._sync_entity_parents()
        
    def _on_sync_parents(self):
        """
        When someone clicks on the "Sync Parents" button
        """
        self._sync_entity_parents()


    def _sync_current_file(self):
        #if not self._p4:
        #    self._connect()
        files_to_sync, total_file_count = self._get_files_to_sync()
        files_to_sync_count = len(files_to_sync)
        if files_to_sync_count == 0:
            msg = "\n <span style='color:#2C93E2'>No Need to sync</span> \n"
            self._add_log(msg, 2)

        elif files_to_sync_count > 0:
            msg = "\n <span style='color:#2C93E2'>Syncing {} files ... </span> \n".format(files_to_sync_count)
            self._add_log(msg, 2)
            #self._do_sync_files_sequential(files_to_sync)
            #self._do_sync_files_ThreadPool(files_to_sync)
            #self._do_sync_files_concurrent_futures(files_to_sync)
            self._do_sync_files_threading_thread_2(files_to_sync)
            #self._do_sync_files_threading_multi_thread(files_to_sync)

            msg = "\n <span style='color:#2C93E2'>Syncing files is complete</span> \n"
            self._add_log(msg, 2)
            msg = "\n <span style='color:#2C93E2'>Reloading data ...</span> \n"
            self._add_log(msg, 2)
            self._status_model.hard_refresh()
            self._publish_file_history_model.hard_refresh()
            # self._publish_type_model.hard_refresh()
            self._publish_model.hard_refresh()
            #for p in self._entity_presets:
            #    self._entity_presets[p].model.hard_refresh()
            self._setup_file_details_panel([])
            # self._get_perforce_summary()

            if self.main_view_mode == self.MAIN_VIEW_COLUMN:
                # self._populate_column_view_widget()
                self._set_thump_view_mode()
                # time.sleep(1)
                # self._set_column_view_mode()

            msg = "\n <span style='color:#2C93E2'>Reloading data is complete</span> \n"
            self._add_log(msg, 2)


    def _sync_entity_parents(self):
        logger.debug("Getting entity parents")
        #logger.debug(">>> self._entity_data {}".format(self._entity_data))

        # logger.debug(">>> getting entity parents")
        self._get_entity_parents(self._entity_data)
        #logger.debug(">>> preparing entity parents published files")
        #self._prepare_entity_parents_published_files()
        logger.debug("Syncing entity parents published files")
        self._sync_entity_parents_published_files()

    def _get_perforce_summary(self):
        """
        When someone clicks on the "Sync" button
        """
        #if not self._p4:
        #    self._connect()
        files_to_sync, total_file_count = self._get_files_to_sync()
        files_to_sync_count = len(files_to_sync)
        if files_to_sync_count == 0:
            msg = "\n <span style='color:#2C93E2'>No Need to sync</span> \n"
            self._add_log(msg, 2)


    ########################################################################################


    # Perforce connection, Sync, and related GUI items
    def _publish_submitted_data_using_publisher_ui(self):
        """
        Publish Depot Data
        """
        selected_item = self._get_selected_entity()
        sg_entity = shotgun_model.get_sg_data(selected_item)

        # logger.debug(">>>>>>>>>>  sg_entity {}".format(sg_entity))

        if self._submitted_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Sending the following unpublished files to the Shotgrid Publisher...</span> \n"
            self._add_log(msg, 2)
            # Create publish file
            out_file = open(self._publish_files_path, 'w')
            out_file.write('Depot Files\n')
            # Create a new Perforce changelist
            desc = "Fixing files "
            change = create_change(self._p4, desc)

            for sg_item in self._submitted_data_to_publish:
                sg_item["entity"] = sg_entity
                if 'path' in sg_item:
                    file_to_publish = sg_item['path'].get('local_path', None)
                    if file_to_publish:
                        msg = "{}".format(file_to_publish)
                        self._add_log(msg, 4)

                        out_file.write('%s\n' % file_to_publish)
                        action = self._get_action(sg_item)
                        #logger.debug(">>>>>>>>>>  file_to_publish: {}".format(file_to_publish))
                        #logger.debug(">>>>>>>>>>  action: {}".format(action))
                        if action:
                            action = self.action_dict.get(action, None)
                            #logger.debug("><<<>>>>>>>>>>>>  action: {}".format(action))
                            #logger.debug("><<<>>>>>>>>>>>>  change: {}".format(change))
                            add_res = add_to_change(self._p4, change, file_to_publish)
                            #logger.debug("><<<>>>>>>>>>>>>  add_res: {}".format(add_res))
                            action_result = self._p4.run(action, "-c", change, "-v", file_to_publish)
                            #logger.debug("><<<>>>>>>>>>>>>  action_result: {}".format(action_result))
                        #action_result = self._p4.run("edit", "-c", change, "-v", file_to_publish)

                        #add_res = add_to_change(self._p4, change, file_to_publish)
                        #action_result = self._p4.run("edit", "-c", change, "-v", file_to_publish)
            out_file.close()

            # Run the publisher UI

            engine = sgtk.platform.current_engine()
            #logger.debug(">>>>>>>>>>  engine is {}".format(engine))

            #logger.debug("<<<<>>>>  engine commands ")
            #for key, value in engine.commands.items():
            #    logger.debug("<<<<>>>>  {}:{}".format(key, value))


            #properties = engine.commands['Publish...']['properties']
            #logger.debug(">>>>>>>>>>  engine commands properties are {}".format(properties))

            engine.commands["Publish..."]["callback"]()

            # msg = "\n <span style='color:#2C93E2'>Publishing files is complete</span> \n"
            # self._add_log(msg, 2)
            msg = "\n <span style='color:#2C93E2'>Reloading data ...</span> \n"
            self._add_log(msg, 2)
            self._reload_treeview()

            msg = "\n <span style='color:#2C93E2'>Updating the Pending View ...</span> \n"
            self._add_log(msg, 2)
            self.update_pending_view()

        else:
            msg = "\n <span style='color:#2C93E2'>Check files in the Pending view to publish using the Shotgrid Publisher</span> \n"
            self._add_log(msg, 2)

        self._submitted_data_to_publish = []



    def _publish_submitted_data_using_command_line_original(self):
        """
        Publish Depot Data
        """
        selected_item = self._get_selected_entity()
        sg_entity = shotgun_model.get_sg_data(selected_item)
        # logger.debug(">>>>>>>>>>  sg_entity {}".format(sg_entity))

        if self._submitted_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Publishing all unpublished files in the depot associated with this entity to Shotgrid ...</span> \n"
            self._add_log(msg, 2)
            files_count = len(self._submitted_data_to_publish)
            for i, sg_item in enumerate(self._submitted_data_to_publish):
                sg_item["entity"] = sg_entity
                if 'path' in sg_item:
                    rev = sg_item.get("version_number") or sg_item.get("headRev") or 1

                    file_to_publish = sg_item['path'].get('local_path', None)
                    msg = "({}/{})  Publishing file: {}#{}".format(i + 1, files_count, file_to_publish, rev)
                    self._add_log(msg, 4)

                    #p4_result = self._p4.run("add", "-v", file_to_publish)
                    #p4_result = self._p4.run("edit", "-v", file_to_publish)
                    #logger.debug("Adding file to perforce: {}".format(p4_result))

                    publisher = PublishItem(sg_item)
                    publish_result = publisher.commandline_publishing()
                    # publish_result = publisher.gui_publishing()
                    if publish_result:
                        logger.debug("New data is: {}".format(publish_result))


            msg = "\n <span style='color:#2C93E2'>Publishing files is complete</span> \n"
            self._add_log(msg, 2)
            msg = "\n <span style='color:#2C93E2'>Reloading data</span> \n"
            self._add_log(msg, 2)
            #self._reload_treeview()

        else:
            msg = "\n <span style='color:#2C93E2'>No need to publish any file</span> \n"
            self._add_log(msg, 2)

        self._submitted_data_to_publish = []


    def _publish_submitted_data_using_command_line(self):
        """
        Publish Depot Data using threading for speedup.
        """
        selected_item = self._get_selected_entity()
        sg_entity = shotgun_model.get_sg_data(selected_item)

        if self._submitted_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Publishing all unpublished files in the depot associated with this entity to Shotgrid ...</span> \n"
            self._add_log(msg, 2)
            files_count = len(self._submitted_data_to_publish)

            # List to store active threads
            threads = []

            # Create and start threads for publishing each file
            for i, sg_item in enumerate(self._submitted_data_to_publish):
                sg_item["entity"] = sg_entity
                if 'path' in sg_item:
                    rev = sg_item.get("version_number") or sg_item.get("headRev") or 1
                    file_to_publish = sg_item['path'].get('local_path', None)
                    msg = "({}/{})  Publishing file: {}#{}".format(i + 1, files_count, file_to_publish, rev)
                    self._add_log(msg, 4)

                    # Create a thread for each publish task
                    thread = threading.Thread(target=self._publish_one_file_thread,
                                              args=(sg_item, file_to_publish, rev))
                    threads.append(thread)
                    thread.start()

            # Wait for all threads to finish
            for thread in threads:
                thread.join()

            msg = "\n <span style='color:#2C93E2'>Publishing files is complete</span> \n"
            self._add_log(msg, 2)
            msg = "\n <span style='color:#2C93E2'>Reloading data</span> \n"
            self._add_log(msg, 2)
            # self._reload_treeview()

        else:
            msg = "\n <span style='color:#2C93E2'>No need to publish any file</span> \n"
            self._add_log(msg, 2)

        self._submitted_data_to_publish = []

    def _publish_one_file_thread(self, sg_item, file_to_publish, rev):
        """
        Publish a single file in a thread.
        """
        publisher = PublishItem(sg_item)
        publish_result = publisher.commandline_publishing()
        if publish_result:
            logger.debug("New data is: {}".format(publish_result))

    def _create_key(self, file_path):
        return file_path.replace("\\", "").replace("/", "").lower() if file_path else None

    def _get_files_to_sync(self):
        """
        Get Perforce Data
        :return:
        """
        total_file_count = 0
        files_to_sync = []

        model = self.ui.publish_view.model()
        for row in range(model.rowCount()):
            model_index = model.index(row, 0)
            proxy_model = model_index.model()
            source_index = proxy_model.mapToSource(model_index)
            # now we have arrived at our model derived from StandardItemModel
            # so let's retrieve the standarditem object associated with the index
            item = source_index.model().itemFromIndex(source_index)

            is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
            if not is_folder:
                # Run default action.
                total_file_count += 1
                sg_item = shotgun_model.get_sg_data(model_index)
                # logger.info("--------->>>>>>  sg_item is: {}".format(sg_item))
                sg_item_path = sg_item.get("path", None)
                if sg_item_path:
                    local_path = sg_item_path.get("local_path", None)

                    if local_path:
                        """
                        action = sg_item.get("action", None)
                        head_action = sg_item.get("headAction", None)
                        
                        if action and action != head_action:
                            files_to_sync.append(local_path)
                            msg = "Publishing file: {}...".format(local_path)
                            self._add_log(msg, 4)
                            publisher = PublishItem(sg_item)
                            publish_result = publisher.commandline_publishing()
                        else:
                        """
                        have_rev = sg_item.get('haveRev', "0")
                        head_rev = sg_item.get('headRev', "0")
                        if self._to_sync(have_rev, head_rev):
                            files_to_sync.append(local_path)

        return files_to_sync, total_file_count

    def _sync_file(self, file_name, i, total):
        # Sync file
        logger.debug("Syncing file: {}".format(file_name))
        logger.debug("i: {}".format(i))
        logger.debug("total: {}".format(total))

        p4_result = self._p4.run("sync", "-f", file_name + "#head")
        logger.debug("p4_result is: {}".format(p4_result))

        if p4_result:
            # Update log
            msg = "({}/{})  Syncing of file {} is complete".format(i + 1, total, file_name)
            self._add_log(msg, 3)
            # Update progress bar
            progress_sum = ((i + 1) / total) * 100
            self.progress_bar(progress_sum)
            #time.sleep(1)
        QCoreApplication.processEvents()

    def _do_sync_files_threads(self, files_to_sync):

        threads = []
        total = len(files_to_sync)
        if total > 0:
            # Creating and starting threads for each file
            for i, file_name in enumerate(files_to_sync):
               
                    msg = "({}/{})  Syncing file: {}...".format(i + 1, total, file_name)
                    self._add_log(msg, 3)
                    thread = threading.Thread(target=self._sync_file, args=(file_name,i, total,))
                    threads.append(thread)
                    #thread.start()
    
            # Start all threads
            max_threads = 5
            count = 1
            while len(threads) > 0:
                if threading.activeCount() <= max_threads:
                    #logger.debug("--------->>>>>>  count: {}".format(count))
                    thread = threads.pop()
                    thread.start()
                    count += 1
    
            # Waiting for all threads to finish
            for thread in threads:
                thread.join()
            #   #thread.wait()
    """
    def _sync_file_threads(self, file_name):
        # Sync file
        logger.debug("--------->>>>>>  Syncing file: {}".format(file_name))

        p4_result = self._p4.run("sync", "-f", file_name + "#head")
        logger.debug("--------->>>>>>  p4_result is: {}".format(p4_result))

        if p4_result:
            # Update log
            msg = "({}/{})  Syncing of file {} is complete".format(i + 1, total, file_name)
            self._add_log(msg, 3)
            # Update progress bar
            progress_sum = ((i + 1) / total) * 100
            self._add_progress_bar(progress_sum)
            #time.sleep(1)
        QCoreApplication.processEvents()
    """

    def _do_sync_files_ThreadPoolExecutor(self, files_to_sync):

        threads = []
        total = len(files_to_sync)
        # Number of parallel threads to use
        num_threads = 3
        if total > 0:

            # Create a ThreadPoolExecutor with the desired number of threads
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                # Submit each file sync task to the executor
                results = [executor.submit(self._sync_file, file_path) for file_path in files_to_sync]

                # Wait for all tasks to complete
                concurrent.futures.wait(results)

    def _do_sync_files_FileSyncThread(self, files_to_sync):

        threads = []
        self.file_queue = queue.Queue()
        total = len(files_to_sync)
        if total > 0:
            # Creating and starting threads for each file
            for i, file_name in enumerate(files_to_sync):
                msg = "({}/{})  Syncing file: {}...".format(i + 1, total, file_name)
                self._add_log(msg, 3)
                self.file_queue.put(file_name)

            num_threads = min(len(files_to_sync), 4)  # Number of threads to use
            for _ in range(num_threads):
                # Creating and starting threads for the file queue
                thread = FileSyncThread(self._p4, self.file_queue)
                thread.start()
                threads.append(thread)

            self.file_queue.join()
            # Waiting for all threads to finish
            #for thread in threads:
            #    thread.join()


    def _do_sync_files_ThreadPool(self, files_to_sync):
        # Sync files
        total = len(files_to_sync)
        if total > 0:
            self.thread_pool = QThreadPool()
            #self.thread_pool = QThreadPool.globalInstance()
            self.thread_pool.setMaxThreadCount(6)  # Set the maximum number of concurrent threads
            for i, file_name in enumerate(files_to_sync):
                msg = "({}/{})  Syncing file: {}...".format(i + 1, total, file_name)
                self._add_log(msg, 3)
                #runnable = SyncRunnable(p4=self._p4, file_name=file_name)
                runnable = self._sync_runnable_file(file_name)
                self.thread_pool.start(runnable)
                progress_sum = ((i + 1) / total) * 100
                self._update_progress(progress_sum)
                QCoreApplication.processEvents()
            self.thread_pool.waitForDone()


    def _do_sync_files_concurrent_futures(self, files_to_sync):
        # Sync files
        total = len(files_to_sync)
        if total > 0:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                futures = []
                for i, file_name in enumerate(files_to_sync):
                    msg = "({}/{})  Syncing file: {}...".format(i + 1, total, file_name)
                    self._add_log(msg, 3)
                    # runnable = SyncRunnable(p4=self._p4, file_name=file_name)
                    runnable = self._sync_runnable_file(file_name)
                    future = executor.submit(runnable)
                    futures.append(future)
                    progress_sum = ((i + 1) / total) * 100
                    self._update_progress(progress_sum)

                # Wait for all tasks to complete
                concurrent.futures.wait(futures)

    def _sync_runnable_file(self, file_name):
        # Sync file
        #logger.debug("--------->>>>>>  Syncing file: {}".format(file_name))

        p4_result = self._p4.run("sync", "-f", file_name + "#head")
        #logger.debug("--------->>>>>>  p4_result is: {}".format(p4_result))

    def _do_sync_files_SyncThread(self, files_to_sync):

        # Creating and starting threads for each file
        threads = []

        progress_sum = 0
        total = len(files_to_sync)
        if total > 0:
            for i, file_name in enumerate(files_to_sync):
                msg = "({}/{})  Syncing file: {}".format(i + 1, total, file_name)
                self._add_log(msg, 3)
                progress_sum = ((i + 1) / total) * 100
                thread = SyncThread(p4=self._p4, file_name=file_name)
                threads.append(thread)
                #thread.start()
                #thread.run()
                self._update_progress(progress_sum)
                QCoreApplication.processEvents()

            # Start all threads
            for thread in threads:
                thread.start()

            # Waiting for all threads to finish
            for thread in threads:
                thread.join()

    def _do_sync_files_sequential(self, files_to_sync):
        
        #Get latest revision
        
        progress_sum = 0
        total = len(files_to_sync)
        if total > 0:
            for i, file_path in enumerate(files_to_sync):
                progress_sum = ((i + 1) / total) * 100
                p4_result = self._p4.run("sync", "-f", file_path + "#head")
                logger.debug("Syncing file: {}".format(file_path))
                msg = "({}/{})  Syncing file: {}".format(i+1, total, file_path)
                self._add_log(msg, 3)
                self._update_progress(progress_sum)

    def _do_sync_files_threading_thread_1(self, files_to_sync):
        self.sync_command = []
        self.sync_command.append("sync")
        self.sync_command.append("-f")
        #parallel_cmd = "--parallel threads=12,batch=8,batchsize=512,min=1,minsize=1"
        #self.sync_command.append(parallel_cmd)

        for i, file_path in enumerate(files_to_sync):
            depot_path = self._get_depot_filepath(file_path)
            depot_path = "{}#head".format(depot_path)
            self.sync_command.append(depot_path)

        logger.debug("sync_command: {}".format(self.sync_command))

        sync_threads = threading.Thread(target=self.run_sync, args=())
        sync_threads.start()
        sync_threads.join()

    def _do_sync_files_threading_thread_2(self, files_to_sync, entity=None):
        self.sync_command = []
        self.sync_command.append("sync")
        self.sync_command.append("-f")
        self.sync_command.append("--parallel")
        self.sync_command.append("threads=16,batch=4,batchsize=4096,min=1,minsize=1")

        for i, file_path in enumerate(files_to_sync):
            depot_path = self._get_depot_filepath(file_path)
            depot_path = "{}#head".format(depot_path)
            self.sync_command.append(depot_path)

        #logger.debug("sync_command: {}".format(self.sync_command))

        sync_thread = threading.Thread(target=self.run_sync, args=())
        sync_thread.start()

        total = len(files_to_sync)
        for i, file_path in enumerate(files_to_sync):

            msg = "({}/{})  Syncing file: {}".format(i + 1, total, file_path)
            self._add_log(msg, 3)
            progress_sum = ((i + 1) / total) * 100
            # Simulate progress
            self._update_progress(progress_sum)
            QCoreApplication.processEvents()
            time.sleep(0.15)
            #time.sleep(0.1)

        msg = "\n <span style='color:#2C93E2'>Finalizing file syncing, please wait...</span> \n"
        self._add_log(msg, 2)

        # Todo, find out why this is faster than sync_thread.join()
        # wait for all threads to complete
        while sync_thread.is_alive():
            #threading.enumerate()
            #logger.debug(">>>>>>>>> len(threading.enumerate()): {}".format(len(threading.enumerate())))
            QCoreApplication.processEvents()

        # wait for all threads to complete
        #sync_thread.join()

    def run_sync_original(self):
        # Sync files
        p4_response = self._p4.run(self.sync_command)
        #logger.debug("p4_response: {}".format(p4_response))
        logger.debug(">>>>>>> Result of syncing file: {}".format(p4_response))

    def run_sync(self):
        # Sync files
        p4_response = self._p4.run(self.sync_command)
        logger.debug("Result of syncing files ..." )
        for entry in p4_response:
            logger.debug("{}".format(entry))

        # Check for errors in the p4_response
        if any(entry.get('error') for entry in p4_response):
            error_messages = [entry['error'] for entry in p4_response if entry.get('error')]
            #raise Exception("File sync failed with errors: {}".format(", ".join(error_messages)))
            logger.error("File sync failed with errors: {}".format(", ".join(error_messages)))

        # The sync was successful
        logger.debug("File sync completed.")

    def _do_sync_files_threading_thread_3(self, files_to_sync):
        self.sync_command = []
        self.sync_command.append("sync")
        self.sync_command.append("-f")
        self.sync_command.append("--parallel")
        self.sync_command.append("threads=12,batch=8,batchsize=512,min=1,minsize=1")

        total_tasks = len(files_to_sync)  # Total number of tasks
        completed_tasks = 0  # Number of completed tasks
        remaining_tasks = total_tasks  # Number of remaining tasks

        semaphore = threading.Semaphore()  # Semaphore to track remaining tasks

        for i, file_path in enumerate(files_to_sync):
            depot_path = self._get_depot_filepath(file_path)
            depot_path = "{}#head".format(depot_path)
            self.sync_command.append(depot_path)

        logger.debug("sync_command: {}".format(self.sync_command))

        sync_thread = threading.Thread(target=self.run_sync_semaphore, args=(files_to_sync, semaphore, completed_tasks))
        sync_thread.start()
        self.update_progress_thread(sync_thread, total_tasks, completed_tasks, remaining_tasks)

    def update_progress_thread(self, thread, total_tasks, completed_tasks, remaining_tasks):
        while thread.is_alive():
            progress = int((completed_tasks / total_tasks) * 100)  # Calculate the progress based on completed tasks
            self.progress_bar.setValue(progress)
            QCoreApplication.processEvents()

    def run_sync_semaphore(self, files_to_sync, semaphore, completed_tasks):
        for file in files_to_sync:
            with semaphore:  # Acquire semaphore to indicate a task in progress
                # Perform the sync operation for file using self.sync_command
                # Update the progress of completed tasks
                completed_tasks += 1

        self.completed_tasks = completed_tasks
        self.remaining_tasks = 0

    def _do_sync_files_threading_multi_thread(self, files_to_sync):
        self.sync_command = []
        self.sync_command.append("sync")
        self.sync_command.append("-f")

        for i, file_path in enumerate(files_to_sync):
            depot_path = self._get_depot_filepath(file_path)
            depot_path = "{}#head".format(depot_path)
            self.sync_command.append(depot_path)

        logger.debug("sync_command: {}".format(self.sync_command))

        sync_threads = []
        for _ in range(len(files_to_sync)):
            thread = threading.Thread(target=self.run_sync, args=())
            sync_threads.append(thread)
            thread.start()

        for thread in sync_threads:
            thread.join()

    def _do_sync_files_subprocess(self, files_to_sync):

        processes = []
        total = len(files_to_sync)
        for i, file_path in enumerate(files_to_sync):
            depot_path = self._get_depot_filepath(file_path)
            depot_path = "{}#head".format(depot_path)
            msg = "({}/{})  Syncing file: {}".format(i + 1, total, file_path)
            self._add_log(msg, 3)
            p = subprocess.Popen(['p4', 'sync', '-f', depot_path])
            processes.append(p)

        for p in processes:
            p.wait()

    def _update_progress(self, value):
        if 100 > value > 0:
            self.ui.progress.setValue(value)
            self.ui.progress.setVisible(True)
        else:
            self.ui.progress.setVisible(False)
        QCoreApplication.processEvents()

    def send_error_message(self, text):
        """
        Send error message
        :param text:
        :return:
        """
        # msg = "\n <span style='color:#FF0000'>{}:</span> \n".format(text)
        # msg = "\n <span style='color:#CC3333'>{}:</span> \n".format(text)
        msg = "\n <span style='color:#d45239'>{}:</span> \n".format(text)
        self._add_log(msg, 2)

    def _add_log(self, msg, flag):
        if flag <= 2:
            msg = "\n{}\n".format(msg)
        else:
            msg = "{}".format(msg)
        self.ui.log_window.append(msg)
        #if flag < 4:
        #    logger.debug(msg)
        self.ui.log_window.verticalScrollBar().setValue(self.ui.log_window.verticalScrollBar().maximum())
        QCoreApplication.processEvents()

    def _to_sync (self, have_rev, head_rev):
        """
        Determine if we should sync the file
        """
        have_rev_int = int(have_rev)
        head_rev_int = int(head_rev)
        if head_rev_int > 0 and have_rev_int < head_rev_int:
            return True
        return False

    def _connect(self):
        """
        Connect to Perforce.  If a connection can't be established with
        the current settings then the connection UI will be shown.
        """
        try:
            if not self._p4:
                logger.debug("Connecting to perforce ...")
                self._fw = sgtk.platform.get_framework("tk-framework-perforce")
                self._p4 = self._fw.connection.connect()
        except:
            #Todo add error message
            logger.debug("Failed to connect!")
            raise
    ########################################################################################
    # cog icon actions

    def _pre_execute_action(self, action):
        """
        Called before a custom action is executed.

        :param action: The QAction that is being executed.
        """
        data = action.data()

        # If there is a single item, we'll put its name in the banner.
        if len(data) == 1:
            sg_data = data[0]["sg_publish_data"]
            name_str = sg_data.get("name") or "Unnamed"
            version_number = sg_data.get("version_number")
            vers_str = "%03d" % version_number if version_number is not None else "N/A"

            self._action_banner.show_banner(
                "<center>Action <b>%s</b> launched on <b>%s Version %s</b></center>"
                % (action.text(), name_str, vers_str)
            )
        else:
            # Otherwise we'll simply mention the selection.
            self._action_banner.show_banner(
                "<center>Action <b>%s</b> launched on selection.</center>"
                % (action.text(),)
            )

        # Force the window to be redrawn and process events right away since the
        # hooks will be run right after this method returns, which wouldn't
        # leave space for the event loop to update the UI.
        self.window().repaint()
        QApplication.processEvents()

    def show_help_popup(self):
        """
        Someone clicked the show help screen action
        """
        app = sgtk.platform.current_bundle()
        help_pix = [
            QPixmap(":/res/help_1.png"),
            QPixmap(":/res/help_2.png"),
            QPixmap(":/res/help_3.png"),
            QPixmap(":/res/help_4.png"),
        ]
        help_screen.show_help_screen(self.window(), app, help_pix)

    def _on_doc_action(self):
        """
        Someone clicked the show docs action
        """
        app = sgtk.platform.current_bundle()
        app.log_debug("Opening documentation url %s..." % app.documentation_url)
        QDesktopServices.openUrl(QUrl(app.documentation_url))

    def _on_reload_action(self):
        """
        Hard reload all caches
        """
        self._status_model.hard_refresh()
        self._publish_file_history_model.hard_refresh()
        self._publish_type_model.hard_refresh()
        self._publish_model.hard_refresh()
        for p in self._entity_presets:
            self._entity_presets[p].model.hard_refresh()
        # self._get_perforce_summary()

    def _on_reload_action_simplified(self):
        """
        Hard reload all caches
        """
        self._status_model.hard_refresh()
        self._publish_file_history_model.hard_refresh()
        self._publish_type_model.hard_refresh()
        self._publish_model.hard_refresh()

    ########################################################################################
    # entity listing tree view and presets toolbar

    def _get_selected_entity(self):
        """
        Returns the item currently selected in the tree view, None
        if no selection has been made.
        """

        selected_item = None
        selection_model = self._entity_presets[
            self._current_entity_preset
        ].view.selectionModel()
        if selection_model.hasSelection():

            current_idx = selection_model.selection().indexes()[0]

            model = current_idx.model()

            if not isinstance(model, (SgHierarchyModel, SgEntityModel)):
                # proxy model!
                current_idx = model.mapToSource(current_idx)

            # now we have arrived at our model derived from StandardItemModel
            # so let's retrieve the standarditem object associated with the index
            selected_item = current_idx.model().itemFromIndex(current_idx)

        return selected_item

    def _select_tab(self, tab_caption, track_in_file_history):
        """
        Programmatically selects a tab based on the requested caption.

        :param str tab_caption: Name of the tab to bring forward.
        :param track_in_file_history: If ``True``, the tab switch will be registered in the
            file_history.
        """
        if tab_caption != self._current_entity_preset:
            for idx in range(self.ui.entity_preset_tabs.count()):
                tab_name = self.ui.entity_preset_tabs.tabText(idx)
                if tab_name == tab_caption:
                    # found the new tab index we should set! now switch tabs.
                    #
                    # first switch the tab widget around but without triggering event
                    # code (this would mean an infinite loop!)
                    self._disable_tab_event_handler = True
                    try:
                        self.ui.entity_preset_tabs.setCurrentIndex(idx)
                    finally:
                        self._disable_tab_event_handler = False
                    # now run the logic for the switching
                    self._switch_profile_tab(idx, track_in_file_history)

    def _select_item_in_entity_tree(self, tab_caption, item):
        """
        Select an item in the entity tree, ensure the tab
        which holds it is selected and scroll to make it visible.

        Item can be None - in this case, nothing is selected.
        """
        # this method is called when someone clicks the home button,
        # clicks the back/forward file_history buttons or double clicks on
        # a folder in the thumbnail UI.

        # there are three basic cases here:
        # 1) we are already on the right tab but need to switch item
        # 2) we are on the wrong tab and need to switch tabs and then switch item
        # 3) we are on the wrong tab and need to switch but there is no item to select

        # Phase 1 - first check if we need to switch tabs
        self._select_tab(tab_caption, item is None)

        # Phase 2 - Now select and zoom onto the item
        view = self._entity_presets[self._current_entity_preset].view
        selection_model = view.selectionModel()

        if item:
            # ensure that the tree view is expanded and that the item we are about
            # to selected is in vertically centered in the widget

            # get the currently selected item in our tab
            selected_item = self._get_selected_entity()

            if selected_item and selected_item.index() == item.index():
                # the item is already selected!
                # because there is no easy way to "kick" the selection
                # model in QT, explicitly call the callback
                # which is normally being called when an item in the
                # treeview gets selected.
                self._on_treeview_item_selected()

            else:
                # we are about to select a new item in the tree view!
                # when we pass selection indices into the view, must first convert them
                # from deep model index into proxy model index style indicies
                proxy_index = view.model().mapFromSource(item.index())
                # and now perform view operations
                view.scrollTo(proxy_index, QAbstractItemView.PositionAtCenter)
                selection_model.select(
                    proxy_index, QItemSelectionModel.ClearAndSelect
                )
                selection_model.setCurrentIndex(
                    proxy_index, QItemSelectionModel.ClearAndSelect
                )
            #if self.main_view_mode == self.MAIN_VIEW_COLUMN:
            #    self._populate_column_view_widget()

        else:
            # clear selection to match no items
            selection_model.clear()

            # note: the on-select event handler will take over at this point and register
            # file_history, handle click logic etc.

    def _recreate_entity_presets(self):
        """
        Loads the entity presets from the configuration and sets up buttons and models
        based on the config.
        """
        app = sgtk.platform.current_bundle()

        # --- Clean up existing presets ---
        try:
            # Disconnect the main tab change signal first
            self.ui.entity_preset_tabs.currentChanged.disconnect(
                self._on_entity_profile_tab_clicked
            )
        except (TypeError, RuntimeError):
            # Signal was likely not connected yet (e.g., first run)
            pass

        # Disconnect signals from individual preset views and clear data
        for preset_name, preset in list(self._entity_presets.items()):
            try:
                if preset.view and preset.view.selectionModel():
                    preset.view.selectionModel().selectionChanged.disconnect(
                        self._on_treeview_item_selected
                    )
            except (TypeError, RuntimeError):
                pass
            # Optionally, explicitly delete widgets if needed, though Qt might handle it
            # if preset.view: preset.view.deleteLater()
            # if preset.model: preset.model.deleteLater() # Be careful with model deletion if shared

        self._entity_presets = {}  # Clear the internal dictionary
        self.ui.entity_preset_tabs.clear()  # Remove all tabs from the UI
        # Consider clearing relevant dynamic widgets if they aren't managed elsewhere
        # self._dynamic_widgets = [] # Or filter based on relevance
        # ---------------------------------

        for setting_dict in app.get_setting("entities"):

            # --- Validate settings ---
            key_error_msg = (
                "Configuration error: 'entities' item %s is missing key '%s'!"
            )
            value_error_msg = "Configuration error: 'entities' item %s key '%s' has an invalid value '%s'!"

            key = "caption"
            if key not in setting_dict:
                raise TankError(key_error_msg % (setting_dict, key))
            preset_name = setting_dict["caption"]

            key = "type"
            value = setting_dict.get(key, "Query") # Default to Query if not specified
            if value not in ("Hierarchy", "Query"):
                raise TankError(value_error_msg % (setting_dict, key, value))
            type_hierarchy = value == "Hierarchy"

            sg_entity_type = None # Initialize
            if type_hierarchy:
                key = "root"
                if key not in setting_dict:
                    raise TankError(key_error_msg % (setting_dict, key))
                sg_entity_type = "Project" # Hierarchy root is typically Project
            else: # Query type
                for key in ("entity_type", "hierarchy", "filters"):
                    if key not in setting_dict:
                        raise TankError(key_error_msg % (setting_dict, key))
                sg_entity_type = setting_dict["entity_type"]

            # Get optional publish_filter setting
            publish_filters = setting_dict.get("publish_filters", []) # Default to empty list
            # -------------------------

            # --- Create models ---
            if type_hierarchy:
                entity_root = self._get_entity_root(setting_dict["root"])
                (model, proxy_model) = self._setup_hierarchy_model(app, entity_root)
            else:
                (model, proxy_model) = self._setup_query_model(app, setting_dict)
            # ---------------------

            # --- Create UI elements ---
            logger.debug(f"[PRESET] Creating tab for preset: {preset_name}")
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)
            self.ui.entity_preset_tabs.addTab(tab, preset_name)

            view = QTreeView(tab)
            layout.addWidget(view)
            view.setModel(proxy_model)
            # ------------------------

            # --- Setup View ---
            view.setEditTriggers(QAbstractItemView.NoEditTriggers)
            view.setProperty("showDropIndicator", False)
            view.setIconSize(QSize(20, 20))
            view.setStyleSheet("QTreeView::item { padding: 6px; }")
            view.setUniformRowHeights(True)
            # ------------------

            # --- "My Tasks" Special Handling ---
            if preset_name == "My Tasks":
                logger.debug("Special handling for 'My Tasks' preset")
                view.setHeaderHidden(False)
                view.header().setStretchLastSection(False) # Don't stretch the last column
                # Set resize modes for columns
                view.header().setSectionResizeMode(0, QHeaderView.Stretch) # Stretch Name column
                view.header().setSectionResizeMode(1, QHeaderView.ResizeToContents) # Resize To Sync column to contents
                view.setSortingEnabled(True)
                view.sortByColumn(0, Qt.AscendingOrder) # Sort by Name initially

                source_model = proxy_model.sourceModel()
                # Ensure model has 2 columns if it doesn't already
                if source_model.columnCount() < 2:
                    source_model.setColumnCount(2)
                source_model.setHorizontalHeaderLabels(["Name", "To Sync"])
                logger.debug(f"[PRESET] Set headers: Name, To Sync")

                # Populate the "To Sync" column (consider doing this async if slow)
                # This part might be better placed in a separate refresh method
                # called after the model is initially populated.
                # For simplicity, doing it here synchronously.
                row_count = source_model.rowCount()
                logger.debug(f"[PRESET] 'My Tasks' initial row count: {row_count}")
                for row in range(row_count):
                    proxy_index_name = proxy_model.index(row, 0)
                    if not proxy_index_name.isValid(): continue
                    source_index_name = proxy_model.mapToSource(proxy_index_name)
                    if not source_index_name.isValid(): continue

                    item_model = source_index_name.model()
                    item = item_model.itemFromIndex(source_index_name)
                    if not item: continue

                    (sg_data, entity_data) = model_item_data.get_item_data(item)
                    entity_path, entity_id, entity_type_task = self._get_entity_info(entity_data)

                    if entity_path:
                        sync_count = self._get_sync_count_for_entity(entity_path)
                        sync_msg = "Up to date" if sync_count == 0 else f"{sync_count} To Sync"
                        sync_icon = self.sync_icons.get_sync_pixmap(sync_count)

                        # Get or create the item for the second column
                        sync_item = source_model.item(source_index_name.row(), 1)
                        if sync_item is None:
                            sync_item = QStandardItem()
                            source_model.setItem(source_index_name.row(), 1, sync_item)

                        sync_item.setText(sync_msg)
                        if sync_icon:
                            sync_item.setIcon(sync_icon)
                        else:
                            sync_item.setIcon(QIcon()) # Clear icon if none
                    else:
                         # Handle cases where path couldn't be determined
                        sync_item = source_model.item(source_index_name.row(), 1)
                        if sync_item is None:
                            sync_item = QStandardItem("N/A")
                            source_model.setItem(source_index_name.row(), 1, sync_item)
                        else:
                            sync_item.setText("N/A")
                        sync_item.setIcon(QIcon())

                logger.debug("Finished special handling for 'My Tasks' preset")
            else:
                view.setHeaderHidden(True)
            # ---------------------------------

            # --- Search Widgets ---
            search_widget_ref = None # Keep a reference for connecting signals later
            if not type_hierarchy: # Query model
                search_layout = QHBoxLayout()
                layout.addLayout(search_layout)

                search_edit = MyLineEdit(tab) # Use custom line edit
                search_edit.setStyleSheet(
                    "QLineEdit{ border-width: 1px; "
                    "background-image: url(:/res/search.png); "
                    "background-repeat: no-repeat; "
                    "background-position: center left; "
                    "border-radius: 5px; "
                    "padding-left:20px; "
                    "margin:4px; "
                    "height:22px; "
                    "}"
                )
                search_edit.setToolTip(
                    "Use the <i>search</i> field to narrow down the items displayed in the tree above."
                )
                try:
                    search_edit.setPlaceholderText("Search...")
                except AttributeError:
                    pass # Placeholder text not available in older Qt versions
                search_layout.addWidget(search_edit)
                search_widget_ref = search_edit # Store reference

                search_button = QPushButton("Search", tab)
                search_button.setToolTip("Click to search for items displayed in the tree above.")
                search_layout.addWidget(search_button)

                clear_search_button = QToolButton(tab)
                clear_icon = QIcon(":/res/clear_search.png")
                clear_search_button.setIcon(clear_icon)
                clear_search_button.setAutoRaise(True)
                clear_search_button.setToolTip("Click to clear your current search.")
                clear_search_button.clicked.connect(lambda checked=False, editor=search_edit: editor.setText("")) # Use default arg trick
                search_layout.addWidget(clear_search_button)

                # Connect search signals
                search_edit.returnPressed.connect(
                    lambda v=view, pm=proxy_model, search=search_edit: self.trigger_search(v, pm, search)
                )
                search_button.clicked.connect(
                    lambda v=view, pm=proxy_model, search=search_edit: self.trigger_search(v, pm, search)
                )

                self._dynamic_widgets.extend([search_layout, search_edit, search_button, clear_search_button, clear_icon])

            else: # Hierarchy model
                hierarchical_search = shotgun_search_widget.HierarchicalSearchWidget(tab)
                hierarchical_search.search_root = entity_root
                hierarchical_search.node_activated.connect(
                    lambda entity_type, entity_id, name, path_label, incremental_paths, v=view, pm=proxy_model: self._node_activated(
                        incremental_paths, v, pm
                    )
                )
                # Connect model signal for when async item retrieval is done
                model.async_item_retrieval_completed.connect(
                    lambda item, v=view, pm=proxy_model: self._async_item_retrieval_completed(
                        item, v, pm
                    )
                )
                hierarchical_search.set_bg_task_manager(self._task_manager)
                layout.addWidget(hierarchical_search)
                search_widget_ref = hierarchical_search # Store reference
                self._dynamic_widgets.append(hierarchical_search)
            # ----------------------

            # --- Context Menus ---
            def action_hovered(action):
                tip = action.toolTip()
                if tip == action.text() or not tip: # Hide if tooltip is same as text or empty
                    QToolTip.hideText()
                else:
                    QToolTip.showText(QCursor.pos(), tip)

            view_actions = []
            if type_hierarchy:
                action_ca = QAction("Collapse All Folders", view)
                action_ca.hovered.connect(lambda act=action_ca: action_hovered(act)) # Use lambda default arg
                action_ca.triggered.connect(view.collapseAll)
                view_actions.append(action_ca)

                action_reset = QAction("Reset", view)
                action_reset.setToolTip(
                    "<nobr>Reset the tree to its root collapsed state.</nobr><br><br>"
                    "Clears existing data, reloads cached data immediately, "
                    "and lazy-loads the rest on navigation."
                )
                action_reset.hovered.connect(lambda act=action_reset: action_hovered(act))
                action_reset.triggered.connect(model.reload_data)
                view_actions.append(action_reset)
            else: # Query type
                action_ea = QAction("Expand All Folders", view)
                action_ea.hovered.connect(lambda act=action_ea: action_hovered(act))
                action_ea.triggered.connect(view.expandAll)
                view_actions.append(action_ea)

                action_ca = QAction("Collapse All Folders", view)
                action_ca.hovered.connect(lambda act=action_ca: action_hovered(act))
                action_ca.triggered.connect(view.collapseAll)
                view_actions.append(action_ca)

                action_refresh = QAction("Refresh", view)
                action_refresh.setToolTip(
                    "<nobr>Refresh tree data from ShotGrid.</nobr><br><br>"
                    "Updates happen in the background. New data is added without affecting selection. "
                    "Modified/deleted data may cause a rebuild, affecting selection."
                )
                action_refresh.hovered.connect(lambda act=action_refresh: action_hovered(act))
                action_refresh.triggered.connect(model.async_refresh)
                view_actions.append(action_refresh)

            view.setContextMenuPolicy(Qt.ActionsContextMenu)
            for act in view_actions:
                view.addAction(act)
            self._dynamic_widgets.extend(view_actions)
            # ---------------------

            # --- Connect Signals ---
            selection_model = view.selectionModel()
            selection_model.selectionChanged.connect(self._on_treeview_item_selected)
            # -----------------------

            # --- Overlay Widget ---
            overlay = ShotgunModelOverlayWidget(model, view)
            # ----------------------

            # --- Store Preset ---
            ep = EntityPreset(
                preset_name, sg_entity_type, model, proxy_model, view, publish_filters
            )
            self._entity_presets[preset_name] = ep
            # Keep references to avoid garbage collection
            self._dynamic_widgets.extend([model, proxy_model, tab, layout, view, selection_model, overlay])
            # --------------------

        # --- Finalize ---
        # Reconnect the main tab change signal
        self.ui.entity_preset_tabs.currentChanged.connect(
            self._on_entity_profile_tab_clicked
        )

        # Initialize by navigating home, ensuring models are ready if async loading
        # Consider using a QTimer.singleShot or connecting to a model loaded signal
        # if data loading is asynchronous and might not be ready immediately.
        # For now, assuming synchronous or fast enough loading.
        if self.ui.entity_preset_tabs.count() > 0:
             # Ensure models are populated before navigating home
             # This might need adjustment based on how models load data
             QCoreApplication.processEvents() # Give models a chance to load initial data
             self._on_home_clicked()
        # ----------------

    def _load_entity_presets(self):
        """
        Loads the entity presets from the configuration and sets up buttons and models
        based on the config.
        """
        app = sgtk.platform.current_bundle()

        for setting_dict in app.get_setting("entities"):

            # Validate that the setting dictionary contains all items needed.
            # Here is an example of Hierarchy setting dictionary:
            #     {'caption': 'Project',
            #      'type':    'Hierarchy',
            #      'root':    '{context.project}'
            # Here is an example of Query setting dictionary:
            #     {'caption':     'My Tasks',
            #      'type':        'Query',
            #      'entity_type': 'Task',
            #      'hierarchy':   ['project', 'entity', 'content'],
            #      'filters':     [['task_assignees', 'is', '{context.user}'],
            #                      ['project.Project.sg_status', 'is', 'Active']]}

            key_error_msg = (
                "Configuration error: 'entities' item %s is missing key '%s'!"
            )
            value_error_msg = "Configuration error: 'entities' item %s key '%s' has an invalid value '%s'!"

            key = "caption"
            if key not in setting_dict:
                raise TankError(key_error_msg % (setting_dict, key))

            preset_name = setting_dict["caption"]

            key = "type"
            if key in setting_dict:
                value = setting_dict[key]
                if value not in ("Hierarchy", "Query"):
                    raise TankError(value_error_msg % (setting_dict, key, value))
                type_hierarchy = value == "Hierarchy"
            else:
                # When the type is not given, default to "Query".
                type_hierarchy = False

            if type_hierarchy:

                key = "root"
                if key not in setting_dict:
                    raise TankError(key_error_msg % (setting_dict, key))

                sg_entity_type = "Project"

            else:

                for key in ("entity_type", "hierarchy", "filters"):
                    if key not in setting_dict:
                        raise TankError(key_error_msg % (setting_dict, key))

                sg_entity_type = setting_dict["entity_type"]

            # get optional publish_filter setting
            # note: actual value in the yaml settings can be None,
            # that's why we cannot use setting_dict.get("publish_filters", [])
            publish_filters = setting_dict.get("publish_filters")
            if publish_filters is None:
                publish_filters = []

            # Create the model.
            if type_hierarchy:
                entity_root = self._get_entity_root(setting_dict["root"])
                (model, proxy_model) = self._setup_hierarchy_model(app, entity_root)
            else:
                (model, proxy_model) = self._setup_query_model(app, setting_dict)


            # ------------------------------------------------------------------------------
            # Add a new tab and its layout to the main tab bar
            logger.debug(f"[PRESET] Creating tab for preset: {preset_name}")
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)
            self.ui.entity_preset_tabs.addTab(tab, preset_name)

            # Create and configure the tree view
            view = QTreeView(tab)
            layout.addWidget(view)
            view.setModel(proxy_model)

            view.setEditTriggers(QAbstractItemView.NoEditTriggers)
            view.setProperty("showDropIndicator", False)
            view.setIconSize(QSize(20, 20))
            view.setStyleSheet("QTreeView::item { padding: 6px; }")
            view.setUniformRowHeights(True)

            if preset_name == "My Tasks":
                logger.debug("Special handling for 'My Tasks' preset")

                # Show two columns: Name and To Sync
                view.setHeaderHidden(False)
                view.header().setStretchLastSection(False)
                view.header().setSectionResizeMode(QHeaderView.Stretch)
                view.setSortingEnabled(True)
                view.sortByColumn(0, Qt.AscendingOrder)

                # Set column headers
                source_model = proxy_model.sourceModel()
                source_model.setHorizontalHeaderLabels(["Name", "To Sync"])
                # logger.debug(f"[PRESET] Set headers: Name, To Sync")

                row_count = source_model.rowCount()
                # logger.debug(f"[PRESET] 'My Tasks' row count: {row_count}")

                for row in range(row_count):
                    # logger.debug(f"------------------------------------------------------------------")
                    proxy_index = proxy_model.index(row, 0)
                    if not proxy_index.isValid():
                        # logger.debug(f"[PRESET] Row {row}: Invalid proxy index")
                        continue

                    source_index = proxy_model.mapToSource(proxy_index)
                    if not source_index.isValid():
                        # logger.debug(f"[PRESET] Row {row}: Invalid source index")
                        continue

                    # Get item using source_index.model(), not base model
                    item_model = source_index.model()
                    item = item_model.itemFromIndex(source_index)

                    if not item:
                        # logger.debug(f"[PRESET] Row {row}: No item in model")
                        continue

                    # Extract the Shotgun data and field value from the node item.
                    (sg_data, entity_data) = model_item_data.get_item_data(item)

                    # logger.debug(">>>>>>>>>>>>>> entity sg_data is: {}".format(sg_data))
                    # logger.debug(">>>>>>>>>>>>>> entity entity_data is: {}".format(entity_data))


                    entity_path, entity_id, entity_type = self._get_entity_info(entity_data)
                    if not entity_id or not entity_type or not entity_path:
                        # logger.debug(
                        #    f"[PRESET] Row {row}: Invalid entity info — Path: {entity_path}, ID: {entity_id}, Type: {entity_type}")
                        continue

                    # logger.debug(f"[PRESET] Row {row}: Entity Path: {entity_path}")
                    # logger.debug(f"[PRESET] Row {row}: Entity ID={entity_id}, Type={entity_type}")

                    sync_count = self._get_sync_count_for_entity(entity_path)
                    # logger.debug(f"[PRESET] Row {row}: Sync count = {sync_count}")

                    # Set value into the second column
                    if sync_count == 0:
                        msg = "Up to date"
                    else:
                        msg = "{} To Sync".format(sync_count)
                    desc_item = QStandardItem(str(msg))
                    sync_icon = self.sync_icons.get_sync_pixmap(sync_count)
                    if sync_icon:
                        desc_item.setIcon(sync_icon)

                    source_model.setItem(source_index.row(), 1, desc_item)
                logger.debug("End of Special handling for 'My Tasks' preset")

            else:
                view.setHeaderHidden(True)
                # logger.debug(f"[PRESET] Using default view setup for preset: {preset_name}")

            # Keep references to avoid garbage collection
            self._dynamic_widgets.extend([model, proxy_model, tab, layout, view])

            #-------------------------------------------------------------------------------

            if not type_hierarchy:

                # FIXME: We should probably remove all of this block in favor of something like. Doesn't quite
                # work at the moment so I'm leaving it as a suggestion to a future reader.
                # search = SearchWidget(tab)
                # search.setToolTip("Use the <i>search</i> field to narrow down the items displayed in the tree above.")
                # search_layout.addWidget(search)
                # search.set_placeholder_text("Search...")
                # search.search_changed.connect(
                #     lambda text, v=view, pm=proxy_model: self._on_search_text_changed(text, v, pm)
                # )

                # Add a layout to host search.
                search_layout = QHBoxLayout()
                layout.addLayout(search_layout)

                # Add the search text field.
                # search = QLineEdit(tab)
                search = MyLineEdit(tab)
                search.setStyleSheet(
                    "QLineEdit{ border-width: 1px; "
                    "background-image: url(:/res/search.png); "
                    "background-repeat: no-repeat; "
                    "background-position: center left; "
                    "border-radius: 5px; "
                    "padding-left:20px; "
                    "margin:4px; "
                    "height:22px; "
                    "}"
                )
                search.setToolTip(
                    "Use the <i>search</i> field to narrow down the items displayed in the tree above."
                )

                """
                try:
                    # This was introduced in Qt 4.7, so try to use it if we can...
                    search.setPlaceholderText("Search...")
                except:
                    pass
                """
                search_layout.addWidget(search)


                # Add a Search button.
                logger.debug("Searching for items in the tree above, query text is {}".format(search.text()))
                search_button = QPushButton("Search", tab)
                search_button.setToolTip("Click to search for items displayed in the tree above.")

                search_layout.addWidget(search_button)



                # Add a cancel search button, disabled by default.
                clear_search = QToolButton(tab)
                icon = QIcon()
                icon.addPixmap(
                    QPixmap(":/res/clear_search.png"),
                    QIcon.Normal,
                    QIcon.Off,
                )
                clear_search.setIcon(icon)
                clear_search.setAutoRaise(True)
                # Ignore the boolean parameter in the lambda. There seems to be an odd bug here,
                # probably in PySide2. Contrary to other places where we simply
                # accept a two parameters, one for the boolean and a second default one,
                # here we have to pass a default value to checked. If we don't, we get
                #   TypeError: <lambda>() missing 1 required positional argument: 'checked'
                #
                clear_search.clicked.connect(
                    lambda checked=True, editor=search: editor.setText("")
                )
                clear_search.setToolTip("Click to clear your current search.")
                search_layout.addWidget(clear_search)

                # logger.debug("Text at time of signal: {}".format(search.get_current_text()))

                # Connect the returnPressed signal to fetch text from get_current_text

                # Setup returnPressed to trigger search with processed events
                search.returnPressed.connect(
                    lambda v=view, pm=proxy_model, search=search: self.trigger_search(v, pm, search)
                )

                search_button.clicked.connect(
                    lambda v=view, pm=proxy_model, search=search: self.trigger_search(v, pm, search)
                )


                # Keep a handle to all the new Qt objects, otherwise the GC may not work.
                self._dynamic_widgets.extend(
                    [search_layout, search, search_button, clear_search, icon]
                )

            else:
                search = shotgun_search_widget.HierarchicalSearchWidget(tab)

                search.search_root = entity_root

                # When a selection is made, we are only interested into the paths to the node so we can refresh
                # the model and expand the item.
                search.node_activated.connect(
                    lambda entity_type, entity_id, name, path_label, incremental_paths, view=view, proxy_model=proxy_model: self._node_activated(
                        incremental_paths, view, proxy_model
                    )
                )
                # When getting back the model items that were loaded, we will need the view and proxy model
                # to expand the item.
                model.async_item_retrieval_completed.connect(
                    lambda item, view=view, proxy_model=proxy_model: self._async_item_retrieval_completed(
                        item, view, proxy_model
                    )
                )
                search.set_bg_task_manager(self._task_manager)
                layout.addWidget(search)

                self._dynamic_widgets.extend([search])

            # We need to handle tool tip display ourselves for action context menus.
            def action_hovered(action):
                tip = action.toolTip()
                if tip == action.text():
                    QToolTip.hideText()
                else:
                    QToolTip.showText(QCursor.pos(), tip)

            # Set up a view right click menu.
            if type_hierarchy:

                action_ca = QAction("Collapse All Folders", view)
                action_ca.hovered.connect(lambda: action_hovered(action_ca))
                action_ca.triggered.connect(view.collapseAll)
                view.addAction(action_ca)
                self._dynamic_widgets.append(action_ca)

                action_reset = QAction("Reset", view)
                action_reset.setToolTip(
                    "<nobr>Reset the tree to its PTR hierarchy root collapsed state.</nobr><br><br>"
                    "Any existing data contained in the tree will be cleared, "
                    "affecting selection and other related states, and "
                    "available cached data will be immediately reloaded.<br><br>"
                    "The rest of the data will be lazy-loaded when navigating down the tree."
                )
                action_reset.hovered.connect(lambda: action_hovered(action_reset))
                action_reset.triggered.connect(model.reload_data)
                view.addAction(action_reset)
                self._dynamic_widgets.append(action_reset)

            else:

                action_ea = QAction("Expand All Folders", view)
                action_ea.hovered.connect(lambda: action_hovered(action_ea))
                action_ea.triggered.connect(view.expandAll)
                view.addAction(action_ea)
                self._dynamic_widgets.append(action_ea)

                action_ca = QAction("Collapse All Folders", view)
                action_ca.hovered.connect(lambda: action_hovered(action_ca))
                action_ca.triggered.connect(view.collapseAll)
                view.addAction(action_ca)
                self._dynamic_widgets.append(action_ca)

                action_refresh = QAction("Refresh", view)
                action_refresh.setToolTip(
                    "<nobr>Refresh the tree data to ensure it is up to date with Flow Production Tracking.</nobr><br><br>"
                    "Since this action is done in the background, the tree update "
                    "will be applied whenever the data is returned from Flow Production Tracking.<br><br>"
                    "When data has been added, it will be added into the existing tree "
                    "without affecting selection and other related states.<br><br>"
                    "When data has been modified or deleted, a tree rebuild will be done, "
                    "affecting selection and other related states."
                )
                action_refresh.hovered.connect(lambda: action_hovered(action_refresh))
                action_refresh.triggered.connect(model.async_refresh)
                view.addAction(action_refresh)
                self._dynamic_widgets.append(action_refresh)

            view.setContextMenuPolicy(Qt.ActionsContextMenu)

            # Set up an on-select callback.
            selection_model = view.selectionModel()
            self._dynamic_widgets.append(selection_model)

            selection_model.selectionChanged.connect(self._on_treeview_item_selected)

            overlay = ShotgunModelOverlayWidget(model, view)
            self._dynamic_widgets.append(overlay)

            # Store all these objects keyed by the caption.
            ep = EntityPreset(
                preset_name, sg_entity_type, model, proxy_model, view, publish_filters
            )

            self._entity_presets[preset_name] = ep

        # hook up an event handler when someone clicks a tab
        self.ui.entity_preset_tabs.currentChanged.connect(
            self._on_entity_profile_tab_clicked
        )

        # finalize initialization by clicking the home button, but only once the
        # data has properly arrived in the model.
        self._on_home_clicked()

    def _get_sync_count_for_entity(self, key):
        """
        Given a ShotGrid entity, return how many files need to be synced for it.
        Includes debug logging for tracing issues.
        """

        # logger.debug(f"[SYNC CHECK] Checking entity: PATH={key}")

        try:
            sync_count = 0
            key = key.rstrip('/')
            # fstat_list = self._p4.run_fstat('-Of', key + '/...')
            fstat_list = self._p4.run_fstat(key + '/...')
            for i, fstat in enumerate(fstat_list):
                if fstat:
                    # logger.debug(f"[SYNC CHECK] fstat {i}: {fstat}")
                    have_rev = fstat.get('haveRev', "0")
                    head_rev = fstat.get('headRev', "0")
                    if self._to_sync(have_rev, head_rev):
                        sync_count += 1

            return sync_count

        except Exception as e:
            logger.warning(f"[SYNC CHECK] Exception during sync check for entity path {key}: {e}")
            return 0

    def trigger_search(self, view, proxy_model, search):
        QApplication.processEvents()  # Process all pending GUI events
        text = search.get_current_text()  # Retrieve the text
        logger.debug("Text at time of search: {}".format(text))
        self._on_search_text_changed(text, view, proxy_model)

    def _get_entity_root(self, root):
        """
        Translates the string from the settings into an entity.

        :param str root: Can be '{context.project} or empty.

        :returns: Entity that will be used for the root.
        """

        app = sgtk.platform.current_bundle()

        # FIXME: API doesn't support non-project entities as the root yet.
        # if root == "{context.entity}":
        #     if app.context.entity:
        #         return app.context.entity
        #     else:
        #         app.log_warning(
        #             "There is no entity in the current context %s. "
        #             "Hierarchy will default to project." % app.context
        #         )
        #         root = "{context.project}"

        if root == "{context.project}":
            if app.context.project:
                return app.context.project
            else:
                app.log_warning(
                    "There is no project in the current context %s. "
                    "Hierarchy will default to site." % app.context
                )
                root = None

        if root is not None:
            app.log_warning(
                "Unknown root was specified: %s. "
                "Hierarchy will default to site." % root
            )

        return None

    def _setup_hierarchy_model(self, app, root):
        """
        Create the model and proxy model required by a hierarchy type configuration setting.

        :param app: :class:`Application`, :class:`Engine` or :class:`Framework` bundle instance
                    associated with the loader.
        :param root: The path to the root of the Shotgun hierarchy to display.
        :return: Created `(model, proxy model)`.
        """

        # If the root is a project, include it in the hierarchy model so that
        # we can display project publishes. We do an innocent little hack here
        # by including a space at the front of the project root item to make it
        # display first in the tree.
        if root.get("type") == "Project":
            include_root = " %s" % (root.get("name", "Project Publishes"),)

        # Construct the hierarchy model and load a hierarchy that leads
        # to entities that are linked via the "PublishedFile.entity" field.
        model = SgHierarchyModel(
            self,
            root_entity=root,
            bg_task_manager=self._task_manager,
            include_root=include_root,
        )

        # Create a proxy model.
        proxy_model = QtGui.QSortFilterProxyModel(self)
        proxy_model.setSourceModel(model)

        # Impose and keep the sorting order on the default display role text.
        proxy_model.sort(0)
        proxy_model.setDynamicSortFilter(True)

        # When clicking on a node, we fetch all the nodes under it so we can populate the
        # right hand-side. Make sure we are notified when the child come back so we can load
        # publishes for the current item.
        model.data_refreshed.connect(self._hierarchy_refreshed)

        return (model, proxy_model)

    def _hierarchy_refreshed(self):
        """
        Slot triggered when the hierarchy model has been refreshed. This allows to show all the
        folder items in the right-hand side for the current selection.
        """
        selected_item = self._get_selected_entity()

        # tell publish UI to update itself
        self._load_publishes_for_entity_item(selected_item)

    def _node_activated(self, incremental_paths, view, proxy_model):
        """
        Called when a user picks a result from the search widget.
        """
        source_model = proxy_model.sourceModel()
        # Asynchronously retrieve the nodes that lead to the item we picked.
        source_model.async_item_from_paths(incremental_paths)

    def _async_item_retrieval_completed(self, item, view, proxy_model):
        """
        Called when the last node from the deep load is loaded.
        """
        # Ask the view to set the current index.
        proxy_idx = proxy_model.mapFromSource(item.index())
        view.setCurrentIndex(proxy_idx)

    def _setup_query_model(self, app, setting_dict):
        """
        Create the model and proxy model required by a query type configuration setting.

        :param app: :class:`Application`, :class:`Engine` or :class:`Framework` bundle instance
                    associated with the loader.
        :param setting_dict: Configuration setting dictionary for a tab.
        :return: Created `(model, proxy model)`.
        """

        # Resolve any magic tokens in the filters.
        resolved_filters = resolve_filters(setting_dict["filters"])
        setting_dict["filters"] = resolved_filters

        # Construct the query model.
        model = SgEntityModel(
            self,
            setting_dict["entity_type"],
            setting_dict["filters"],
            setting_dict["hierarchy"],
            self._task_manager,
        )

        # Create a proxy model.
        proxy_model = SgEntityProxyModel(self)
        proxy_model.setSourceModel(model)

        return (model, proxy_model)

    def _on_search_text_changed(self, pattern, tree_view, proxy_model):
        """
        Triggered when the text in a search editor changes.

        :param pattern: new contents of search box
        :param tree_view: associated tree view.
        :param proxy_model: associated proxy model
        """
        logger.debug("Search for text: {} ".format(pattern))
        # tell proxy model to reevaulate itself given the new pattern.
        proxy_model.setFilterFixedString(pattern)

        # change UI decorations based on new pattern.
        # for performance, make sure filtering only kicks in
        # once we have typed a couple of characters
        if pattern and len(pattern) >= constants.TREE_SEARCH_TRIGGER_LENGTH:
            # indicate with a blue border that a search is active
            tree_view.setStyleSheet(
                """
                QTreeView {{
                    border-width: 3px;
                    border-style: solid;
                    border-color: {highlight};
                }}
                QTreeView::item {{
                    padding: 6px;
                }}
                """.format(
                    highlight=self.palette().highlight().color().name()
                )
            )
            # expand all nodes in the tree
            tree_view.expandAll()
        else:
            # revert to default style sheet
            tree_view.setStyleSheet("QTreeView::item { padding: 6px; }")

    def _on_entity_profile_tab_clicked(self):
        """
        Called when someone clicks one of the profile tabs
        """
        if not self._disable_tab_event_handler:
            curr_tab_index = self.ui.entity_preset_tabs.currentIndex()
            self._switch_profile_tab(curr_tab_index, track_in_file_history=True)

    def _switch_profile_tab(self, new_index, track_in_file_history):
        """
        Switches to use the specified profile tab.

        :param new_index: tab index to switch to
        :param track_in_file_history: Hint to this method that the actions should be tracked in the
            file_history.
        """
        # qt returns unicode/qstring here so force to str
        curr_tab_name = shotgun_model.sanitize_qt(
            self.ui.entity_preset_tabs.tabText(new_index)
        )

        # and set up which our currently visible preset is
        self._current_entity_preset = curr_tab_name

        # The hierarchy model cannot handle "Show items in subfolders" mode.
        if isinstance(
            self._entity_presets[self._current_entity_preset].model, SgHierarchyModel
        ):
            self.ui.show_sub_items.hide()
        else:
            self.ui.show_sub_items.show()

        if self._file_history_navigation_mode == False:
            # When we are not navigating back and forth as part of file_history navigation,
            # ask the currently visible view to (background async) refresh its data.
            # Refreshing the data only makes sense for SgEntityModel based tabs since
            # SgHierarchyModel does not yet support this kind of functionality.
            model = self._entity_presets[self._current_entity_preset].model
            if isinstance(model, SgEntityModel):
                model.async_refresh()

        if track_in_file_history:
            # figure out what is selected
            selected_item = self._get_selected_entity()

            # update breadcrumbs
            self._populate_entity_breadcrumbs(selected_item)

            # add file_history record
            self._add_file_history_record(self._current_entity_preset, selected_item)

            # tell details view to clear
            self._setup_file_details_panel([])

            # tell the publish view to change
            self._load_publishes_for_entity_item(selected_item)

    def _get_entity_info(self, entity_data):
        """
        Get entity path
        """
        entity_path, entity_id, entity_type = None, 0, None
        # logger.debug(">>>>>>>>>>>>>> entity_data is: {}".format(entity_data))
        if entity_data:
            entity_id = entity_data.get('id', 0)
            entity_type = entity_data.get('type', None)
            if entity_type:
                if entity_type in ["Task"]:
                    entity = entity_data.get("entity", None)
                    if entity:
                        entity_id = entity.get('id', 0)
                        entity_type = entity.get('type', None)

            entity_path = self._app.sgtk.paths_from_entity(entity_type, entity_id)
            # logger.debug(">>>>>>>>>>>>>> entity_id is: {}".format(entity_id))
            # logger.debug(">>>>>>>>>>>>>> entity_type is: {}".format(entity_type))
            # logger.debug(">>>>>>>>>>>>>> entity_path is: {}".format(entity_path))

            if entity_path and len(entity_path) > 0:
                entity_path = entity_path[-1]
                # msg = "\n <span style='color:#2C93E2'>Entity path: {}</span> \n".format(entity_path)
                # self._add_log(msg, 2)
        return entity_path, entity_id, entity_type

    def _create_current_user_task_filesystem_structure_original(self):
        """ Create a folder structure for the current user's tasks """
        # Get the current user's ID
        try:
            user = login.get_current_user(self._app.sgtk)
            # logger.debug("Current user is {}".format(user))
            current_user_id = user.get("id", None)

            if not current_user_id:
                logger.debug("Could not get current user id")
                return

            #project = self._app.shotgun.find_one("Project", [["name", "is", sg_project_name]], ["id"])
            project = self._app.context.project
            if not project:
                logger.debug("Could not get current project")
                return

            # Define the list of statuses you want to filter by
            sg_status_list = ["ip", "rdy", "hld", "rev"]

            # Find all tasks for the current user with the specified statuses
            filters = [
                ["project", "is", project],
                ["task_assignees", "is", {"type": "HumanUser", "id": current_user_id}],
                ["sg_status_list", "in", sg_status_list],
            ]

            fields = ["content", "entity", "entity.Shot", "entity.Asset"]

            tasks = self._app.shotgun.find("Task", filters, fields)
            # logger.debug("Current user tasks are {}".format(tasks))
            # Create folders for each entity associated with the tasks
            for task in tasks:
                entity = task.get("entity", None)
                # logger.debug("User task entity is: {}".format(entity))
                if entity:
                    entity_id = entity.get("id", None)
                    entity_type = entity.get("type", None)
                    if entity_type and entity_id:
                        try:
                            paths_from_entity = self._app.sgtk.paths_from_entity(entity_type, entity_id)
                            #logger.debug("paths_from_entity is: {}".format(paths_from_entity))
                            if paths_from_entity and len(paths_from_entity) > 0:
                                result = self._check_paths_exist(paths_from_entity)
                                if not result:
                                    logger.debug("Paths do not exist for entity:{} on user system".format(entity))
                                    logger.debug("Creating folder structure for entity: {} ...".format(entity))
                                    self._app.sgtk.create_filesystem_structure(entity_type, entity_id)
                                else:
                                    logger.debug("Paths {} exist for entity: {} on user system".format(paths_from_entity, entity))
                            else:
                                logger.debug("No paths exist for entity:{} on SG".format(entity))
                                logger.debug("Creating folder structure for entity:{} ...".format(entity))
                                self._app.sgtk.create_filesystem_structure(entity_type, entity_id)

                        except Exception as e:
                            msg = "\n Unable to create file system structure for entity: {}, {} \n".format(entity_id, e)
                            logger.debug(msg)
                            pass
        except Exception as e:
            msg = "\n Unable to create file system structure for entity\n"
            logger.debug(msg)
            pass

    def _create_current_user_task_filesystem_structure(self):
        """Spawns a background thread to create a folder structure for the current user's tasks."""
        thread = threading.Thread(target=self._task_operations)
        thread.start()

    def _task_operations(self):
        """Handle the creation of folder structure in a background thread."""
        try:
            user = login.get_current_user(self._app.sgtk)
            current_user_id = user.get("id", None)
            if not current_user_id:
                logger.debug("Could not get current user id")
                return

            project = self._app.context.project
            if not project:
                logger.debug("Could not get current project")
                return

            sg_status_list = ["ip", "rdy", "hld", "rev"]
            filters = [
                ["project", "is", project],
                ["task_assignees", "is", {"type": "HumanUser", "id": current_user_id}],
                ["sg_status_list", "in", sg_status_list],
            ]
            fields = ["content", "entity", "entity.Shot", "entity.Asset"]
            tasks = self._app.sgtk.shotgun.find("Task", filters, fields)

            for task in tasks:
                entity = task.get("entity", None)
                if entity:
                    entity_id = entity.get("id", None)
                    entity_type = entity.get("type", None)
                    if entity_type and entity_id:
                        self._create_or_verify_paths(entity_type, entity_id)

        except Exception as e:
            logger.error(f"Error creating file system structure: {e}")

    def _create_or_verify_paths(self, entity_type, entity_id):
        try:
            paths_from_entity = self._app.sgtk.paths_from_entity(entity_type, entity_id)
            if paths_from_entity and len(paths_from_entity) > 0:
                if not self._check_paths_exist(paths_from_entity):
                    self._app.sgtk.create_filesystem_structure(entity_type, entity_id)
            else:
                self._app.sgtk.create_filesystem_structure(entity_type, entity_id)
        except Exception as e:
            logger.error(f"Unable to create or verify file system structure for {entity_type} {entity_id}: {e}")

    def _check_paths_exist(self, paths):
        """
        Check if the paths exist on disk
        """
        result = True
        for path in paths:
            if not os.path.exists(path):
                result = False
        return result

    def _create_filesystem_structure(self, entity_data):
        """
        Get entity path
        """
        active_sg_status_list = ["ip", "rdy", "hld", "rev"]
        entity_path, entity_id, entity_type = None, 0, None
        # logger.debug(">>>>>>>>>>>>>> entity_data is: {}".format(entity_data))
        if entity_data:
            entity_id = entity_data.get('id', 0)
            entity_type = entity_data.get('type', None)
            entity_name = entity_data.get('name', None)
            if entity_type:
                if entity_type in ["Task"]:
                    entity = entity_data.get("entity", None)
                    if entity:
                        entity_id = entity.get('id', 0)
                        entity_type = entity.get('type', None)
                        entity_name = entity.get('name', None)
                        # Create SG file system structure
                        try:
                            sg_status = entity_data.get('sg_status_list', None)
                            #logger.debug(">>>>>>>>>>>>>> sg_status is: {}".format(sg_status))
                            if sg_status in active_sg_status_list:
                                entity_path = self._app.sgtk.paths_from_entity(entity_type, entity_id)
                                #logger.debug(">>>>>>>>>>>>>> current entity_path is: {}".format(entity_path))
                                # self._app.sgtk.synchronize_filesystem_structure()
                                # if not entity_path or len(entity_path) == 0 or not os.path.exists(entity_path[0]):
                                msg = "\n <span style='color:#2C93E2'>Creating file system structure for entity: id:{}, name: {}, path:{} ...</span> \n".format(
                                    entity_id, entity_name, entity_path)
                                self._add_log(msg, 2)
                                if entity_type and entity_id:
                                    self._app.sgtk.create_filesystem_structure(entity_type, entity_id)
                                    #if entity_name:
                                    #    self.update_entity_name(entity_type, entity_id, entity_name, "success")
                                """
                                entity_path = self._app.sgtk.paths_from_entity(entity_type, entity_id)
                                if entity_path and len(entity_path) > 0:
                                    entity_path = entity_path[-1]
                                    msg = "\n <span style='color:#2C93E2'>Entity path: {}</span> \n".format(entity_path)
                                    self._add_log(msg, 2)
                                """

                        except Exception as e:
                            #if entity_name:
                            #    self.update_entity_name(entity_type, entity_id, entity_name, "failure")
                            msg = "\n Unable to create file system structure for entity: {}, {} \n".format(
                                entity_id, e)
                            self._add_log(msg, 4)
                            pass

    def update_entity_name(self, entity_type, entity_id, entity_name, action):

        try:
            new_name = entity_name
            if action == "failure" and "!" in entity_name:
                new_name = entity_name.replace("!", "")
            if action == "failure" and "!" not in entity_name:
                # red_exclamation = "<span style='color:#ff0000'>!</span>"
                red_exclamation = "!"
                new_name = "{}{}".format(entity_name, red_exclamation)
            if action == "success" and "!" in entity_name:
                new_name = entity_name.replace("!", "")
            #logger.debug(">>>>>>>>>>>>>> new entity name is: {}".format(new_name))
            # Update the entity name using sg.update()

            self._app.shotgun.update(entity_type, entity_id, {'code': new_name})
            #logger.debug(">>>>>>>>>>>>>> Reloading entity presets: {}".format(new_name))
            self._load_entity_presets()
        except Exception as e:
            # Handle any exceptions that may occur during the update
            logger.debug("Unable to update entity name for {}: {}".format(entity_name, e))

            pass

    def _on_treeview_item_selected(self):
        """
        Slot triggered when someone changes the selection in a treeview.
        """
        #logger.debug("view_mode is: {}".format(self.main_view_mode))
        self._fstat_dict = {}
        self._entity_data, item = self._reload_treeview()

        # logger.debug(">>>>>>>>>>1 In _on_treeview_item_selected entity_data is: {}".format(self._entity_data))

        self._entity_path, entity_id, entity_type = self._get_entity_info(self._entity_data)

        # Create SG file system structure
        # self._create_filesystem_structure(self._entity_data)

        # logger.debug(">>>>>>>>>>>>>>>>>> self._entity_path: {}".format(self._entity_path))

        model = self.ui.publish_view.model()
        # logger.debug(">>>>>>>>>>2 In _on_treeview_item_selected model.rowCount() is {}".format(model.rowCount()))

        if model.rowCount() > 0:
            self.get_current_sg_data()
        else:
            self.get_current_publish_data(entity_id, entity_type)

        self._update_perforce_data()
        self.print_publish_data()

        #logger.debug("main_view_mode is: {}".format(self.main_view_mode))
        if self.main_view_mode == self.MAIN_VIEW_COLUMN:
            self._populate_column_view_widget()
        if self.main_view_mode == self.MAIN_VIEW_SUBMITTED:
            self._populate_submitted_widget()

        # if Show details is checked, populate the shotgun panel
        #if self.ui.details_tab.isVisible():
        #    logger.debug(">>>>>>>>>>  Populating shotgun panel widget")
        self._get_shotgun_panel_widget()

        # self. _clean_sg_data()


    def get_current_sg_data(self):
        total_file_count = 0
        self._sg_data = []
        self._submitted_data_to_publish = []
        try:
            model = self.ui.publish_view.model()
            # logger.debug(">>>>>>>>>> In get_current_sg_data model.rowCount() is {}".format(model.rowCount()))
            if model.rowCount() > 0:
                for row in range(model.rowCount()):
                    model_index = model.index(row, 0)
                    proxy_model = model_index.model()
                    source_index = proxy_model.mapToSource(model_index)
                    item = source_index.model().itemFromIndex(source_index)

                    is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
                    if not is_folder:
                        # Run default action.
                        total_file_count += 1
                        sg_item = shotgun_model.get_sg_data(model_index)
                        action = sg_item.get("action") or sg_item.get("headAction") or None
                        if action and action in ["delete"]:
                            # remove the item from the model
                            # logger.debug(">>>>>>>>>>  Removing item: {}".format(sg_item))
                            model.removeRow(row)
                            # remove the model_index from the model
                            # model.removeRow(model_index.row())

                        else:
                            self._sg_data.append(sg_item)
        except:
            pass


    def get_current_publish_data(self, entity_id, entity_type):
        self._sg_data = []
        logger.debug("Entity type is {}".format(entity_type))
        if entity_id and entity_type:
            filters = [[]]
            if entity_type == "Asset":
                filters = [
                     ["entity.Asset.id", "is", entity_id],
                ]
            elif entity_type == "Shot":
                filters = [
                    ["entity.Shot.id", "is", entity_id],
                ]
            elif entity_type == "Task":
                filters = [
                    ["task.Task.id", "is", entity_id],
                ]

            entity_published_files = self._app.shotgun.find(
                "PublishedFile",
                filters,
                ["entity", "path_cache", "path", "version_number", "step"],
                #["entity", "path_cache", "path", "version_number", "name", "description", "created_at", "created_by", "image", "published_file_type", "task","],
            )
            """
            # Exclude published files associated with child entities
            published_files = []
            for published_file in entity_published_files:
                if published_file["entity"]["id"] == entity_id:
                    published_files.append(published_file)
            """

            # self._sg_data = published_files
            self._sg_data = entity_published_files
            #logger.debug(">>>>>>>>>>  Published files are: {}".format(self._sg_data))
        else:
            logger.debug("Unable to get current publish data, entity_id or entity_type is None")

    def _update_perforce_data(self):
        #logger.debug(">>>>>>>>>>  _get_perforce_data: START")
        msg = "\n <span style='color:#2C93E2'>Retrieving Data from Perforce...</span> \n"
        self._add_log(msg, 2)
        self._get_perforce_data()
        msg = "\n <span style='color:#2C93E2'>Perforce Data Retrieval Completed Successfully</span> \n"
        self._add_log(msg, 2)

        """
        #self._publish_model.async_refresh()
        msg = "\n <span style='color:#2C93E2'>Updating data ...</span> \n"
        self._add_log(msg, 2)
        logger.debug(">>>>>>>>>>  update_fstat_data...")
        self._update_fstat_data()
       
        logger.debug(">>>>>>>>>>  fix_fstat_dict...")
        self._fix_fstat_dict()
        """


        # self._get_depot_files_to_publish()

        #msg = "\n <span style='color:#2C93E2'>Soft refreshing data ...</span> \n"
        #self._add_log(msg, 2)
        #logger.debug(">>>>>>>>>>  publish_model.async_refresh...")
        self._publish_model.async_refresh()
        #logger.debug(">>>>>>>>>>  _get_perforce_data: DONE")


    def print_publish_data(self):
        if self._submitted_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>List of unpublished depot files:</span> \n"
            self._add_log(msg, 2)
            for sg_item in self._submitted_data_to_publish:
                if 'path' in sg_item:
                    file_to_publish = sg_item['path'].get('local_path', None)
                    msg = "{}".format(file_to_publish)
                    self._add_log(msg, 4)
            msg = "\n <span style='color:#2C93E2'>Click on 'Fix Files' to publish above files</span> \n"
            self._add_log(msg, 2)

    def _update_fstat_data(self):
        """Update the fstat data for the selected entity"""
        # Get the selected item
        selected_item = self._get_selected_entity()
        # Get the entity data
        entity_data = self._load_publishes_for_entity_item(selected_item)
        # Get the entity path, id and type
        self._entity_path, entity_id, entity_type = self._get_entity_info(entity_data)
        # Get the current publish data
        self.get_current_publish_data(entity_id, entity_type)

        if self._fstat_dict:
            if self._sg_data:
                for sg_item in self._sg_data:
                    # logger.debug(">>>>>>>>>>Checking for published file ...")
                    #logger.debug(">>>>>>>>>>sg_item {}".format(sg_item))
                    sg_item_path = sg_item.get("path", None)
                    if sg_item_path:
                        if "local_path" in sg_item_path:
                            local_path = sg_item_path.get("local_path", None)
                            key = self._create_key(local_path)
                            version_number = sg_item.get("version_number", None)
                            # Get the version number from the path if it exists
                            if version_number:
                                version_number = int(version_number)
                                key = "{}#{}".format(key, version_number)
                            else:
                                # Get the revision number from the path if it exists
                                have_rev = sg_item.get("haveRev", None)
                                if have_rev:
                                    have_rev = int(have_rev)
                                    key = "{}#{}".format(key, have_rev)
                                else:
                                    key = "{}#{}".format(key, 1)
                            depot_file = sg_item.get('depotFile', None)
                            #if depot_file:
                            #    if 'Original_maleLeather_pants' in depot_file:
                            #        logger.debug(">>>>>>>>>  sg_item is: {}".format(sg_item))
                            #        logger.debug(">>>>>>>>>> key is {}".format(key))

                            if key and key in self._fstat_dict:
                                self._fstat_dict[key]["Published"] = True

    def _fix_fstat_dict(self):

        for key in self._fstat_dict:
            file_path = self._fstat_dict[key].get("clientFile", None)
            #logger.debug("----->>>>>>>    self._fstat_dict[key]: {}".format(self._fstat_dict[key]))
            # logger.debug("----->>>>>>>    file_path: {}".format(file_path))
            if file_path:
                self._fstat_dict[key]["name"] = os.path.basename(file_path)
                self._fstat_dict[key]["path"] = {}
                self._fstat_dict[key]["path"]["local_path"] = file_path

            #have_rev = self._fstat_dict[key].get('haveRev', "0")
            head_rev = self._fstat_dict[key].get('headRev', "0")
            #self._fstat_dict[key]["revision"] = "#{}/{}".format(have_rev, head_rev)
            self._fstat_dict[key]["code"] = "{}#{}".format(self._fstat_dict[key].get("name", None), head_rev)
            p4_status = self._fstat_dict[key].get("headAction", None)
            self._fstat_dict[key]["sg_status_list"] = self._get_p4_status(p4_status)

            self._fstat_dict[key]["depot_file_type"] = self._get_publish_type(file_path)
            """
            depot_path = self._fstat_dict[key].get("depotFile", None)
            if depot_path:
                description, p4_user = self._get_file_log(depot_path, head_rev)
                if description:
                    self._fstat_dict[key]["description"] = description
                if p4_user:
                    self._fstat_dict[key]["p4_user"] = p4_user
            """

            #self._submitted_data_to_publish.append(sg_item)

    def _get_submitted_changelists(self, folder_path):

        changes = self._p4.run_changes('-s', 'submitted', folder_path + '/...')

        for change in changes:
            key = change['change']
            if key not in self._submitted_changes:
                self._submitted_changes[key] = change


    def _get_depot_files_to_publish(self):
        for key, sg_item in self._fstat_dict.items():
            if not sg_item.get("Published"):
                file_path = sg_item.get("clientFile")
                if file_path:
                    sg_item.update({
                        "name": os.path.basename(file_path),
                        "path": {"local_path": file_path},
                        "revision": "#{}/{}".format(sg_item.get('haveRev', '0'), sg_item.get('headRev', '0')),
                        "code": "{}#{}".format(os.path.basename(file_path), sg_item.get('headRev', '0')),
                        "sg_status_list": self._get_p4_status(sg_item.get("headAction")),
                        "depot_file_type": self._get_publish_type(file_path)
                    })
                    depot_path = sg_item.get("depotFile")
                    if depot_path:
                        description, p4_user = self._get_file_log(depot_path, sg_item.get('headRev', '0'))
                        if description:
                            sg_item["description"] = description
                        if p4_user:
                            sg_item["p4_user"] = p4_user

                    self._submitted_data_to_publish.append(sg_item)

    def _on_publish_folder_action_original(self, action):
        selected_indexes = self.ui.publish_view.selectionModel().selectedIndexes()
        for model_index in selected_indexes:
            proxy_model = model_index.model()
            source_index = proxy_model.mapToSource(model_index)
            item = source_index.model().itemFromIndex(source_index)

            is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
            if is_folder:
                sg_item = shotgun_model.get_sg_data(model_index)
                #logger.debug(">>>>>>>>>>  sg_item is: {}".format(sg_item))
                if not sg_item:
                    msg = "\n <span style='color:#2C93E2'>Unable to get item data</span> \n"
                    self._add_log(msg, 2)
                    continue
                entity_type = sg_item.get('type', None)
                entity_id = sg_item.get('id', None)
                if entity_type and entity_id:
                    logger.debug("action is: {}".format(action))
                    if action in ["preview"]:
                        msg = "\n <span style='color:#2C93E2'>Generating a preview of the folders, please stand by...</span> \n"
                        self._add_log(msg, 2)
                        self._preview_filesystem_structure(entity_type, entity_id, verbose_mode=True)
                    elif action in ["create"]:
                        msg = "\n <span style='color:#2C93E2'>Creating folders, please stand by...</span> \n"
                        self._add_log(msg, 2)
                        paths_not_on_disk = self._preview_filesystem_structure(entity_type, entity_id, verbose_mode=False)
                        self._create_filesystem_structure_for_folder(entity_type, entity_id, paths_not_on_disk)
                    elif action in ["unregister"]:
                        msg = "\n <span style='color:#2C93E2'>Unregistering folders, please stand by...</span> \n"
                        self._add_log(msg, 2)
                        self._unregister_folders(entity_type, entity_id)
                else:
                    msg = "\n <span style='color:#CC3333'>No entities specified!</span> \n"
                    self._add_log(msg, 2)

    def _unregister_folders_original(self, entity_type, entity_id):
        """
        Unregister folders for the specified entity
        """

        try:

            uf = self._app.sgtk.get_command("unregister_folders")
            #logger.debug(">>>>>>>>>>  uf command is: {}".format(uf))
            message_list = []

            tk = sgtk.sgtk_from_entity(entity_type, entity_id)
            if entity_type == "Task":
                parent_entity = self._app.shotgun.find_one("Task",
                                    [["id", "is", entity_id]],
                                    ["entity"]).get("entity")
                result = uf.execute({"entity": {"type": parent_entity["type"], "id": parent_entity["id"]}})
                message_list.append(result)
            else:
                result = uf.execute({"entity": {"type": entity_type, "id": entity_id}})
                message_list.append(result)
            tk.synchronize_filesystem_structure()


        except Exception as e:
            # other errors are not expected and probably bugs - here it's useful with a callstack.
            msg = "\n <span style='color:#CC3333'>Error when unregistering folders: {}</span> \n".format(e)
            self._add_log(msg, 2)

        else:
            # report back to user
            if message_list and len(message_list) > 0:
                msg = "\n <span style='color:#2C93E2'>Unregistered Folders:</span> \n"
                self._add_log(msg, 2)
                for message in message_list:
                    self._add_log(message, 3)



    def _create_filesystem_structure_for_folder_original(self, entity_type, entity_id, paths_not_on_disk):
        if len(paths_not_on_disk) == 0:
            msg = "\n <span style='color:#2C93E2'>No folders would be generated on disk for this item!</span> \n"
            self._add_log(msg, 2)
            return

        paths_created = []
        try:
            tk = sgtk.sgtk_from_entity(entity_type, entity_id)
            entities_processed = self._app.sgtk.create_filesystem_structure(entity_type, entity_id)
            tk.synchronize_filesystem_structure()

        except Exception as e:
            # other errors are not expected and probably bugs - here it's useful with a callstack.
            msg = "\n <span style='color:#CC3333'>Error when creating folders!, {}</span> \n".format(e)
            self._add_log(msg, 2)

        else:
            # report back to user
            if len(paths_not_on_disk) > 0:
                for path in paths_not_on_disk:
                    # If the path exist on disk, add it to paths_created
                    if os.path.exists(path):
                        paths_created.append(path)

                if len(paths_created) > 0:
                    if len(paths_created) == 1:
                        msg = "\n <span style='color:#2C93E2'>The following {} folder has been created on disk.</span> \n".format(len(paths_created))
                    else:
                        msg = "\n <span style='color:#2C93E2'>The following {} folders have been created on disk.</span> \n".format(len(paths_created))
                    self._add_log(msg, 2)
                    for path in paths_created:
                        self._add_log(path, 3)


    def _preview_filesystem_structure_original(self, entity_type, entity_id, verbose_mode=True):
        paths = []
        paths_not_on_disk = []
        try:
            paths.extend(
                self._app.sgtk.preview_filesystem_structure(entity_type, entity_id)
            )

        except Exception as e:
            # other errors are not expected and probably bugs - here it's useful with a callstack.
            msg = "\n <span style='color:#CC3333'>Error when previewing folders!, {}</span> \n".format(e)
            self._add_log(msg, 2)

        else:
            # success! report back to user
            if len(paths) == 0:
                msg = "\n <span style='color:#2C93E2'>*No folders would be generated on disk for this item!*</span> \n"
                self._add_log(msg, 2)

            else:
                # msg = "\n <span style='color:#2C93E2'>Creating folders would generate {} items on disk: </span> \n".format(len(paths))
                # self._add_log(msg, 2)

                for path in paths:
                    path.replace(r"\_", r"\\_")
                    # If the path doesn't exist on disk, add it to paths_not_on_disk
                    if not os.path.exists(path):
                        paths_not_on_disk.append(path)
                self._add_log("", 3)

                if paths_not_on_disk:
                    if verbose_mode:
                        if len(paths_not_on_disk) == 1:
                            msg = "\n <span style='color:#2C93E2'>The following {} folder is not currently present on the disk and will be created:</span> \n".format(len(paths_not_on_disk))
                        else:
                            msg = "\n <span style='color:#2C93E2'>The following {} folders are not currently present on the disk and will be created:</span> \n".format(len(paths_not_on_disk))
                        self._add_log(msg, 2)
                        for path in paths_not_on_disk:
                            self._add_log(path, 3)
                        self._add_log("", 3)
                if paths and not paths_not_on_disk:
                    if verbose_mode:
                        msg = "\n <span style='color:#2C93E2'>All folders are currently present on the disk and will not be created!</span> \n"
                        self._add_log(msg, 2)

            return paths_not_on_disk


    def _on_publish_folder_action(self, action):
        selected_indexes = self.ui.publish_view.selectionModel().selectedIndexes()
        threads = []
        errors = []

        def thread_function(entity_type, entity_id):
            try:
                result = self._handle_folder_creation(entity_type, entity_id)
                self._add_log(result, 2)
            except Exception as e:
                errors.append(f"Error when creating folders for entity {entity_type} {entity_id}: {e}")

        for model_index in selected_indexes:
            proxy_model = model_index.model()
            source_index = proxy_model.mapToSource(model_index)
            item = source_index.model().itemFromIndex(source_index)

            is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
            if is_folder:
                sg_item = shotgun_model.get_sg_data(model_index)
                if not sg_item:
                    msg = "\n <span style='color:#2C93E2'>Unable to get item data</span> \n"
                    self._add_log(msg, 2)
                    continue

                entity_type = sg_item.get('type', None)
                entity_id = sg_item.get('id', None)
                if entity_type and entity_id:
                    if action == "preview":
                        msg = "\n <span style='color:#2C93E2'>Generating a preview of the folders, please stand by...</span> \n"
                        self._add_log(msg, 2)
                        self._preview_filesystem_structure(entity_type, entity_id, verbose_mode=True)
                    elif action == "create":
                        msg = "\n <span style='color:#2C93E2'>Creating folders, please stand by...</span> \n"
                        self._add_log(msg, 2)

                        # Start a new thread for each folder creation task
                        thread = threading.Thread(target=thread_function, args=(entity_type, entity_id))
                        threads.append(thread)
                        thread.start()
                    elif action == "unregister":
                        msg = "\n <span style='color:#2C93E2'>Unregistering folders, please stand by...</span> \n"
                        self._add_log(msg, 2)
                        self._unregister_folders(entity_type, entity_id)
                else:
                    msg = "\n <span style='color:#CC3333'>No entities specified!</span> \n"
                    self._add_log(msg, 2)

        # Wait for all threads to finish
        for thread in threads:
            thread.join()

        # Handle errors after all threads have finished
        if errors:
            for error in errors:
                msg = f"\n <span style='color:#CC3333'>{error}</span> \n"
                self._add_log(msg, 2)

    def _unregister_folders(self, entity_type, entity_id):
        try:
            uf = self._app.sgtk.get_command("unregister_folders")
            message_list = []

            tk = sgtk.sgtk_from_entity(entity_type, entity_id)
            if entity_type == "Task":
                parent_entity = self._app.shotgun.find_one("Task",
                                                           [["id", "is", entity_id]],
                                                           ["entity"]).get("entity")
                result = uf.execute({"entity": {"type": parent_entity["type"], "id": parent_entity["id"]}})
                message_list.append(result)
            else:
                result = uf.execute({"entity": {"type": entity_type, "id": entity_id}})
                message_list.append(result)
            tk.synchronize_filesystem_structure()

        except Exception as e:
            msg = "\n <span style='color:#CC3333'>Error when unregistering folders: {}</span> \n".format(e)
            self._add_log(msg, 2)
        else:
            if message_list:
                msg = "\n <span style='color:#2C93E2'>Unregistered Folders:</span> \n"
                self._add_log(msg, 2)
                for message in message_list:
                    self._add_log(message, 3)

    def _create_filesystem_structure_for_folder(self, entity_type, entity_id, paths_not_on_disk):
        if len(paths_not_on_disk) == 0:
            msg = "\n <span style='color:#2C93E2'>No folders would be generated on disk for this item!</span> \n"
            self._add_log(msg, 2)
            return

        paths_created = []
        try:
            tk = sgtk.sgtk_from_entity(entity_type, entity_id)
            entities_processed = self._app.sgtk.create_filesystem_structure(entity_type, entity_id)
            tk.synchronize_filesystem_structure()

            for path in paths_not_on_disk:
                if os.path.exists(path):
                    paths_created.append(path)

            if len(paths_created) > 0:
                if len(paths_created) == 1:
                    msg = "\n <span style='color:#2C93E2'>The following folder has been created on disk:</span> \n".format(
                        len(paths_created))
                else:
                    msg = "\n <span style='color:#2C93E2'>The following folders have been created on disk:</span> \n".format(
                        len(paths_created))
                self._add_log(msg, 2)
                for path in paths_created:
                    self._add_log(path, 3)

        except Exception as e:
            msg = "\n <span style='color:#CC3333'>Error when creating folders!, {}</span> \n".format(e)
            self._add_log(msg, 2)

    def _preview_filesystem_structure(self, entity_type, entity_id, verbose_mode=True):
        paths = []
        paths_not_on_disk = []
        try:
            paths.extend(
                self._app.sgtk.preview_filesystem_structure(entity_type, entity_id)
            )
        except Exception as e:
            msg = "\n <span style='color:#CC3333'>Error when previewing folders!, {}</span> \n".format(e)
            self._add_log(msg, 2)
        else:
            if len(paths) == 0:
                msg = "\n <span style='color:#2C93E2'>*No folders would be generated on disk for this item!*</span> \n"
                self._add_log(msg, 2)
            else:
                for path in paths:
                    path.replace(r"\_", r"\\_")
                    if not os.path.exists(path):
                        paths_not_on_disk.append(path)
                self._add_log("", 3)

                if paths_not_on_disk:
                    if verbose_mode:
                        if len(paths_not_on_disk) == 1:
                            msg = "\n <span style='color:#2C93E2'>The following folder is not currently present on the disk and will be created:</span> \n".format(
                                len(paths_not_on_disk))
                        else:
                            msg = "\n <span style='color:#2C93E2'>The following folders are not currently present on the disk and will be created:</span> \n".format(
                                len(paths_not_on_disk))
                        self._add_log(msg, 2)
                        for path in paths_not_on_disk:
                            self._add_log(path, 3)
                        self._add_log("", 3)
                if paths and not paths_not_on_disk:
                    if verbose_mode:
                        msg = "\n <span style='color:#2C93E2'>All folders are currently present on the disk and will not be created!</span> \n"
                        self._add_log(msg, 2)

            return paths_not_on_disk

    def _handle_folder_creation(self, entity_type, entity_id):
        paths_not_on_disk = self._preview_filesystem_structure(entity_type, entity_id, verbose_mode=False)
        if len(paths_not_on_disk) == 0:
            return "\n <span style='color:#2C93E2'>No folders would be generated on disk for this item!</span> \n"

        paths_created = []
        try:
            tk = sgtk.sgtk_from_entity(entity_type, entity_id)
            entities_processed = self._app.sgtk.create_filesystem_structure(entity_type, entity_id)
            tk.synchronize_filesystem_structure()

            for path in paths_not_on_disk:
                if os.path.exists(path):
                    paths_created.append(path)

            if len(paths_created) > 0:
                if len(paths_created) == 1:
                    return "\n <span style='color:#2C93E2'>The following folder has been created on disk:</span> \n" + '\n'.join(
                        paths_created)
                else:
                    return "\n <span style='color:#2C93E2'>The following folders have been created on disk:</span> \n" + '\n'.join(
                        paths_created)

        except Exception as e:
            raise Exception(f"Error when creating folders for entity {entity_type} {entity_id}: {e}")

    def _add_plural(self, word, items):
        """
        appends an s if items > 1
        """
        if items > 1:
            return "%ss" % word
        else:
            return word


    def _on_publish_model_action(self, action):
        selected_actions = []
        selected_files_to_revert = []
        selected_indexes = self.ui.publish_view.selectionModel().selectedIndexes()
        self._submitted_data_to_publish = []
        for model_index in selected_indexes:
            proxy_model = model_index.model()
            source_index = proxy_model.mapToSource(model_index)
            item = source_index.model().itemFromIndex(source_index)

            is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
            if not is_folder:
                sg_item = shotgun_model.get_sg_data(model_index)

                if "path" in sg_item:
                    if "local_path" in sg_item["path"]:
                        target_file = sg_item["path"].get("local_path", None)
                        depot_file = sg_item.get("depotFile", None)
                        if action in ["fix"]:
                            published_file_type = sg_item.get("published_file_type", None)
                            if published_file_type not in ["PublishedFile"]:
                                msg = "Fixing file {} ...".format(target_file)
                                self._add_log(msg, 3)
                                self._submitted_data_to_publish.append(sg_item)
                            else:
                                msg = "Cannot fix file {} as it is already published.".format(target_file)
                                self._add_log(msg, 2)

                        if action in ["add", "move/add", "edit", "delete"]:
                            sg_item_action = sg_item.get("action", None)
                            if sg_item_action and sg_item_action == "delete":
                                msg = "Cannot perform the action on the file {} as it has already been marked for deletion or is deleted.".format(
                                    depot_file)

                                self._add_log(msg, 2)
                                continue

                            if action == "delete":
                                msg = "Marking file {} for deletion ...".format(depot_file)
                            else:
                                msg = "{} file {}".format(action, depot_file)
                            self._add_log(msg, 2)
                            selected_actions.append((sg_item, action))


                        elif action == "revert":

                            # Collect files to revert instead of reverting immediately

                            if target_file:
                                selected_files_to_revert.append(target_file)

                                msg = "Preparing to revert file {} ...".format(target_file)

                                self._add_log(msg, 3)

        if self._submitted_data_to_publish:
            self._on_fix_list()

        # --- Perform bulk revert after the loop ---
        if action == "revert" and selected_files_to_revert:
            try:
                msg = f"Reverting {len(selected_files_to_revert)} selected file(s)..."
                self._add_log(msg, 2)
                # Use argument unpacking (*) to pass all files at once
                p4_result = self._p4.run("revert", *selected_files_to_revert)
                logger.debug(f"Bulk revert result: {p4_result}")
                if p4_result:  # Check if the command was successful (might need adjustment based on p4python output)
                    self.refresh_publish_data()  # Refresh data once after bulk operation
            except Exception as e:
                logger.error(f"Error during bulk revert: {e}")
                self._add_log(f"Error during bulk revert: {e}", 2)  # Show error in log window
        if selected_actions:
            self.perform_changelist_selection(selected_actions)
        #logger.debug(">>>>>>>>>>  publish_model.async_refresh...")
        self._publish_model.async_refresh()


    def perform_changelist_selection(self, selected_actions):
        perform_action = ChangelistSelection(self._p4, selected_actions=selected_actions, parent=self)
        perform_action.show()


    def refresh_publish_data(self):
        self._update_perforce_data()
        self._publish_model.hard_refresh()
        # self._publish_model.async_refresh()

    # Todo: Fix this if needed
    def _pubish_file_for_deletion(self, sg_item, depot_file):

        # Publish the file for deletion
        # Get the entity info
        entity_path, entity_id, entity_type = self._get_entity_info(sg_item)

        filters = [[]]
        if entity_type == "Asset":
            filters = [
                ["entity.Asset.id", "is", entity_id],
            ]
        elif entity_type == "Shot":
            filters = [
                ["entity.Shot.id", "is", entity_id],
            ]
        elif entity_type == "Task":
            filters = [
                ["task.Task.id", "is", entity_id],
            ]

        entity_published_files = self._app.shotgun.find(
            "PublishedFile",
            filters,
            ["entity", "path_cache", "path", "version_number"],
            #["entity", "path_cache", "path", "version_number", "id", "code", "created_at", "user"],
            # ["entity", "path_cache", "path", "version_number", "name", "description", "created_at", "created_by", "image", "published_file_type", "task","],
        )
        entity_versions = self._app.shotgun.find(
            "Version",
            filters,
            ["entity", "path_cache", "path", "version_number"],
            #["entity", "path_cache", "path", "version_number", "id", "code", "created_at", "user"],
            # ["entity", "path_cache", "path", "version_number", "name", "description", "created_at", "created_by", "image", "published_file_type", "task","],
        )

        #logger.debug(">>>> entity_published_files: {}", entity_published_files)
        #logger.debug(">>>> entity_versions: {}", entity_versions)



        """
        logger.debug(">>>> sg_item to publish: {}", sg_item)
        msg = "Publishing file for deletion: {}".format(depot_file)
        self._add_log(msg, 3)

        publisher = PublishItem(sg_item)
        publish_result = publisher.commandline_publishing()
        """



    def _get_treeview_entity(self):
        """
        Slot triggered when someone changes the selection in a treeview.
        """
        selected_item = self._get_selected_entity()

        # update breadcrumbs
        self._populate_entity_breadcrumbs(selected_item)

        # when an item in the treeview is selected, the child
        # nodes are displayed in the main view, so make sure
        # they are loaded.
        model = self._entity_presets[self._current_entity_preset].model
        if selected_item and model.canFetchMore(selected_item.index()):
            model.fetchMore(selected_item.index())


        # notify file_history
        self._add_file_history_record(self._current_entity_preset, selected_item)

        # tell details panel to clear itself
        self._setup_file_details_panel([])

        # tell publish UI to update itself
        sg_data = self._load_publishes_for_entity_item(selected_item)
        return sg_data

    def _reload_treeview(self):
        """
        Slot triggered when someone changes the selection in a treeview.
        """
        selected_item = self._get_selected_entity()

        # update breadcrumbs
        self._populate_entity_breadcrumbs(selected_item)

        # when an item in the treeview is selected, the child
        # nodes are displayed in the main view, so make sure
        # they are loaded.
        model = self._entity_presets[self._current_entity_preset].model
        if selected_item and model.canFetchMore(selected_item.index()):
            model.fetchMore(selected_item.index())

        # notify file_history
        self._add_file_history_record(self._current_entity_preset, selected_item)

        # tell details panel to clear itself
        self._setup_file_details_panel([])

        # tell publish UI to update itself
        sg_data = self._load_publishes_for_entity_item(selected_item)
        return sg_data, selected_item

    def _load_publishes_for_entity_item(self, item):
        """
        Given an item from the treeview, or None if no item
        is selected, prepare the publish area UI.
        """

        # clear selection. If we don't clear the model at this point,
        # the selection model will attempt to pair up with the model is
        # data is being loaded in, resulting in many many events
        sg_data = {}
        self.ui.publish_view.selectionModel().clear()

        # Determine the child folders.
        child_folders = []
        proxy_model = self._entity_presets[self._current_entity_preset].proxy_model

        if item is None:
            # nothing is selected, bring in all the top level
            # objects in the current tab
            num_children = proxy_model.rowCount()

            for x in range(num_children):
                # get the (proxy model) index for the child
                child_idx_proxy = proxy_model.index(x, 0)
                # switch to shotgun model index
                child_idx = proxy_model.mapToSource(child_idx_proxy)
                # resolve the index into an actual standarditem object
                i = self._entity_presets[
                    self._current_entity_preset
                ].model.itemFromIndex(child_idx)
                child_folders.append(i)

        else:
            # we got a specific item to process!

            # now get the proxy model level item instead - this way we can take search into
            # account as we show the folder listings.
            root_model_idx = item.index()
            root_model_idx_proxy = proxy_model.mapFromSource(root_model_idx)
            num_children = proxy_model.rowCount(root_model_idx_proxy)

            # get all the folder children - these need to be displayed
            # by the model as folders

            for x in range(num_children):
                # get the (proxy model) index for the child
                child_idx_proxy = root_model_idx_proxy.child(x, 0)
                # switch to shotgun model index
                child_idx = proxy_model.mapToSource(child_idx_proxy)
                # resolve the index into an actual standarditem object
                i = self._entity_presets[
                    self._current_entity_preset
                ].model.itemFromIndex(child_idx)
                child_folders.append(i)

        # Is the show child folders checked?
        # The hierarchy model cannot handle "Show items in subfolders" mode.
        show_sub_items = self.ui.show_sub_items.isChecked() and not isinstance(
            self._entity_presets[self._current_entity_preset].model, SgHierarchyModel
        )

        if show_sub_items:
            # indicate this with a special background color
            color = self.palette().highlight().color()
            self.ui.publish_view.setStyleSheet(
                "#publish_view {{ background-color: rgba({red}, {green}, {blue}, 20%); }}".format(
                    red=color.red(), green=color.green(), blue=color.blue()
                )
            )
            if len(child_folders) > 0:
                # delegates are rendered in a special way
                # if we are on a non-leaf node in the tree (e.g there are subfolders)
                self._publish_thumb_delegate.set_sub_items_mode(True)
                self._publish_list_delegate.set_sub_items_mode(True)
            else:
                # we are at leaf level and the subitems check box is checked
                # render the cells
                self._publish_thumb_delegate.set_sub_items_mode(False)
                self._publish_list_delegate.set_sub_items_mode(False)
        else:
            self.ui.publish_view.setStyleSheet("")
            self._publish_thumb_delegate.set_sub_items_mode(False)
            self._publish_list_delegate.set_sub_items_mode(False)

        # now finally load up the data in the publish model
        publish_filters = self._entity_presets[
            self._current_entity_preset
        ].publish_filters
        sg_data = self._publish_model.load_data(
            item, child_folders, show_sub_items, publish_filters
        )
        #logger.info(">>>>>>>>>>>>>>>>>>>>>>> item is {}".format(item))
        #logger.info(">>>> child_folders is {}".format(child_folders))
        #logger.info(">>>> show_sub_items is {}".format(show_sub_items))
        #logger.info(">>>> publish_filters is {}".format(publish_filters))
        #logger.info(">>>> sg_data is {}".format(sg_data))
        return sg_data


    def _populate_entity_breadcrumbs(self, selected_item):
        """
        Computes the current entity breadcrumbs

        :param selected_item: Item currently selected in the tree view or
                              `None` when no selection has been made.
        """

        crumbs = []

        if selected_item:

            # figure out the tree view selection,
            # walk up to root, list of items will be in bottom-up order...
            tmp_item = selected_item
            while tmp_item:

                # Extract the Shotgun data and field value from the node item.
                (sg_data, field_value) = model_item_data.get_item_data(tmp_item)

                # now figure out the associated value and type for this node

                if sg_data:
                    # leaf node
                    name = str(field_value)
                    sg_type = sg_data.get("type")

                elif (
                    isinstance(field_value, dict)
                    and "name" in field_value
                    and "type" in field_value
                ):
                    name = field_value["name"]
                    sg_type = field_value["type"]

                elif isinstance(field_value, list):
                    # this is a list of some sort. Loop over all elements and extrat a comma separated list.
                    formatted_values = []
                    if len(field_value) == 0:
                        # no items in list
                        formatted_values.append("No Value")
                    for v in field_value:
                        if isinstance(v, dict) and "name" in v and "type" in v:
                            # This is a link field
                            if v.get("name"):
                                formatted_values.append(v.get("name"))
                        else:
                            formatted_values.append(str(v))

                    name = ", ".join(formatted_values)
                    sg_type = None

                else:
                    # other value (e.g. intermediary non-entity link node like sg_asset_type)
                    name = str(field_value)
                    sg_type = None

                # now set up the crumbs
                if sg_type is None:
                    crumbs.append(name)

                else:
                    # lookup the display name for the entity type:
                    sg_type_display_name = shotgun_globals.get_type_display_name(
                        sg_type
                    )
                    crumbs.append("<b>%s</b> %s" % (sg_type_display_name, name))
                tmp_item = tmp_item.parent()

        # lastly add the name of the tab
        crumbs.append("<b>%s</b>" % self._current_entity_preset)

        breadcrumbs = " <span style='color:#2C93E2'>&#9656;</span> ".join(crumbs[::-1])

        self.ui.entity_breadcrumbs.setText("<big>%s</big>" % breadcrumbs)

    ################################################################################################
    def _convert_local_to_depot_original(self, local_directory):

        local_directory = os.path.abspath(local_directory)
        where_output = self._p4.run_where(local_directory)

        depot_directory = None
        for mapping in where_output:
            depot_directory = mapping.get('depotFile')
            if depot_directory:
                break

        return depot_directory


    def _convert_local_to_depot(self, local_path):
        """
        Converts a local file path to a Perforce depot path.

        Args:
            local_path (str): The local file path.

        Returns:
            str: The corresponding depot path.
        """
        # Remove the drive letter (e.g., B:) and leading backslash
        depot_path = local_path[2:].lstrip("\\")
        # Replace backslashes with forward slashes
        depot_path = depot_path.replace("\\", "/")
        # Add the depot prefix (e.g., "//")
        depot_path = f"//{depot_path}"
        return depot_path

    def _convert_local_to_depot_2(self, local_directory):
        """
        Converts a local file/directory path to its Perforce depot path.

        Args:
            local_directory (str): The local path to be converted.

        Returns:
            str: The depot path corresponding to the local path, or None if not found.
        """
        # Ensure the input path is absolute
        local_directory = os.path.abspath(local_directory)

        try:
            # Run the Perforce `where` command
            where_output = self._p4.run_where(local_directory)
        except Exception as e:
            # Log the exception if the command fails
            logger.error(f"Failed to run `p4 where` for {local_directory}: {e}")
            return None

        # Validate the output of `run_where`
        if not where_output or not isinstance(where_output, list):
            logger.error(f"`p4 where` returned invalid data for {local_directory}: {where_output}")
            return None

        # Attempt to find the depot path
        depot_directory = None
        for mapping in where_output:
            if isinstance(mapping, dict):
                depot_directory = mapping.get('depotFile')
                if depot_directory:
                    break
            else:
                logger.warning(f"Unexpected mapping format for {local_directory}: {mapping}")

        if depot_directory:
            # Return the found depot path
            logger.debug(f"Depot path for {local_directory} is {depot_directory}")
            return depot_directory
        else:
            # Log a warning if no mapping was found
            logger.warning(f"No depot mapping found for {local_directory}")
            return None

    def _get_perforce_data(self):
        """
        Get large Perforce data
        """
        self._item_path_dict = defaultdict(int)
        self._fstat_dict = {}
        self._submitted_changes = {}
        self._submitted_data_to_publish = []

        logger.debug("Entity path is: {}".format(self._entity_path))

        if self._entity_path:
            self._item_path_dict[self._entity_path] += 1
        elif self._sg_data:
            for sg_item in self._sg_data:
                sg_item_path = sg_item.get("path", None)
                if sg_item_path:
                    local_path = sg_item_path.get("local_path", None)
                    if local_path:
                        item_path = os.path.dirname(local_path)
                        self._item_path_dict[item_path] += 1

        for key in self._item_path_dict:
            if key:
                #logger.debug(">>>>>>>>>>  key is: {}".format(key))
                key = self._convert_local_to_depot(key)
                #logger.debug(">>>>>>>>>> Converted key is: {}".format(key))
                key = key.rstrip('/')
                #logger.debug(">>>>>>>>>> modifed key is: {}".format(key))
                fstat_list = self._p4.run_fstat('-Of', key + '/...')
                self._get_submitted_changelists(key)
                # logger.debug(">>>>>>>>>>  self._submitted_changes is: {}".format(self._submitted_changes))

                for fstat in fstat_list:
                    if isinstance(fstat, list) and len(fstat) == 1:
                        fstat = fstat[0]

                    client_file = fstat.get('clientFile', None)

                    if client_file:
                        newkey = self._create_key(client_file)
                        head_rev = fstat.get('headRev', "0")
                        newkey = "{}#{}".format(newkey, head_rev)
                        have_rev = fstat.get('haveRev', "0")

                        if newkey not in self._fstat_dict:
                            self._fstat_dict[newkey] = fstat
                            self._fstat_dict[newkey]['Published'] = False
                            self._fstat_dict[newkey]["revision"] = "#{}/{}".format(have_rev, head_rev)
                            #self._fstat_dict[newkey]["code"] = "{}#{}".format(fstat.get("name", None),head_rev)
                            #self._fstat_dict[newkey]["depot_file_type"] = self._get_publish_type(client_file)
                            #self._fstat_dict[newkey]["name"] = os.path.basename(client_file)
                            #self._fstat_dict[newkey]["path"] = {}
                            #self._fstat_dict[newkey]["path"]["local_path"] = client_file


                            action = fstat.get('action', None) or fstat.get('headAction', None)
                            if action:
                                sg_status = self._get_p4_status(action)
                                if sg_status:
                                    self._fstat_dict[newkey]['sg_status_list'] = sg_status
                            # get the user and description for submitted changelists
                            change = fstat.get('headChange', None)
                            if change and change in self._submitted_changes:
                                self._fstat_dict[newkey]['p4_user'] = self._submitted_changes[change]['user']
                                self._fstat_dict[newkey]['description'] = self._submitted_changes[change]['desc']
                        # logger.debug(">>>>>>>>>> self._fstat_dict[newkey] is: {}".format(self._fstat_dict[newkey]))


    def _get_file_log(self, file_path, head_rev):
        try:
            file_path = f"{file_path}#{head_rev}"
            filelog_list = self._p4.run("filelog", file_path)

            if filelog_list:
                filelog = filelog_list[0]
                desc = filelog.get("desc", [""])[0].lstrip('- ').strip()
                user = filelog.get("user", [""])[0]
                return desc, user
            else:
                return None, None
        except Exception as e:
            return None, None


    def _get_publish_type(self, publish_path):
        """
        Get a publish type
        """
        publish_type = None
        publish_path = os.path.splitext(publish_path)
        if len(publish_path) >= 2:
            extension = publish_path[1]

            # ensure lowercase and no dot
            if extension:
                extension = extension.lstrip(".").lower()
                publish_type = self.settings.get(extension, None)
                if not publish_type:
                    # publish type is based on extension
                    publish_type = "%s File" % extension.capitalize()
            else:
                # no extension, assume it is a folder
                publish_type = "Folder"
        return publish_type

    def _get_p4_status(self, p4_status):
        return self.status_dict.get(p4_status.lower(), None)


    def _get_item_path (self, local_path):
        """
        Get item path
        """
        item_path = ""
        if local_path:
            local_path = local_path.split("\\")
            local_path = local_path[:7]
            item_path = "\\".join(local_path)
        return item_path

    def _get_small_peforce_data(self, sg_data):
        """"
        Get small perforce data
        """

        if sg_data:
            for i, sg_item in enumerate(sg_data):
                if "path" in sg_item:
                    sg_item_path = sg_item.get("path", None)
                    if sg_item_path:
                        local_path = sg_item_path.get("local_path", None)
                    # logger.debug(">>>>>>> local_path is: {}".format(local_path))
                        if local_path:
                            fstat_list = self._p4.run("fstat", local_path)
                            # logger.debug("fstat_list: {}".format(fstat_list))
                            fstat = fstat_list[0]
                            # logger.debug("fstat is: {}".format(fstat))
                            have_rev = fstat.get('haveRev', "0")
                            head_rev = fstat.get('headRev', "0")
                            sg_item["haveRev"], sg_item["headRev"] = have_rev, head_rev
                            sg_item["revision"] = "{}/{}".format(have_rev, head_rev )
                            # logger.debug("{}: Revision: {}".format(i, sg_item["revision"]))
                            # sg_item['depotFile'] = fstat.get('depotFile', None)

            # logger.debug("{}: SG item: {}".format(i, sg_item))

        return sg_data

    def _get_latest_revision(self, files_to_sync):
        for file_path in files_to_sync:
            p4_result = self._p4.run("sync", "-f", file_path + "#head")
            logger.debug("Syncing file: {}".format(file_path))

    def _get_depot_filepath(self, local_path):
        
        #Convert local path to depot path
        #For example, convert: 'B:\\Ark2Depot\\Content\\Base\\Characters\\Human\\Survivor\\Armor\\Cloth_T3\\_ven\\MDL\\Survivor_M_Armor_Cloth_T3_MDL.fbx'
        #to "//Ark2Depot/Content/Base/Characters/Human/Survivor/Armor/Cloth_T3/_ven/MDL/Survivor_M_Armor_Cloth_T3_MDL.fbx"
        
        local_path = local_path[2:]
        depot_path = local_path.replace("\\", "/")
        depot_path = "/{}".format(depot_path)
        return depot_path


    def _find_task_context(self, path):
        # Try to get the context more specifically from the path on disk
        tk = sgtk.sgtk_from_path(path)
        context = tk.context_from_path(path)

        if not context:
            self.log_debug(f"{path} does not correspond to any context!")
            return None

        # In case the task folder is not registered for some reason, we can try to find it
        if not context.task:
            # Publishing Asset
            if context.entity["type"] == "CustomEntity03":
                # We can only hope to match this file if it already is in a Step folder
                if context.step:
                    file_name = os.path.splitext(os.path.basename(path))[0]
                    # Get all the possible tasks for this Asset Step
                    context_tasks = context.sgtk.shotgun.find("Task", [["entity", "is", context.entity],
                                                                       ["step", "is", context.step]], ["content"])
                    for context_task in context_tasks:
                        # Build the regex pattern using https://regex101.com/r/uK8Ca4/1
                        task_name = context_task.get("content")
                        regex = r"\S*(" + re.escape(task_name) + r"){1}(?:_\w*)?$"
                        matches = re.finditer(regex, file_name)
                        for matchNum, match in enumerate(matches, start=1):
                            for group in match.groups():
                                # Assuming there is only ever one match since the match is at the end of the string
                                if group == task_name:
                                    return tk.context_from_entity("Task", context_task["id"])
                                    # Cinematics
            elif context.entity["type"] == "Sequence" or context.entity["type"] == "Shot":
                if context.step:
                    return self._find_context(tk, context, path)
            # All other entities
            else:
                # This is either an Asset root or an Animation
                if not context.step:
                    context_entity = context.sgtk.shotgun.find_one(context.entity["type"],
                                                                   [["id", "is", context.entity["id"]]],
                                                                   ["sg_asset_parent", "sg_asset_type"])
                    # Must be an animation...
                    if context_entity.get("sg_asset_type") == "Animations":
                        return self._find_context(tk, context, path)

                elif context.step['name'] == "Animations":
                    return self._find_context(tk, context, path)

                elif context.step['name'] != "Animations":
                    # file_folder = os.path.basename(os.path.dirname(path))
                    step_tasks = context.sgtk.shotgun.find("Task", [["entity", "is", context.entity],
                                                                    ["step", "is", context.step]],
                                                           ['content', 'step', 'sg_status_list'])
                    step_tasks_list = [task for task in step_tasks if task['step'] == context.step]
                    if len(step_tasks_list) == 1:
                        return tk.context_from_entity("Task", step_tasks_list[0]["id"])
                    else:
                        try:
                            active_tasks = [task for task in step_tasks if task[
                                'sg_status_list'] not in inactive_task_states]  # context.sgtk.shotgun.find_one("Task", [["content", "is", file_folder],["entity", "is", context.entity],["step", "is", context.step]])
                            if len(active_tasks) == 1:
                                return tk.context_from_entity("Task", active_tasks[0]["id"])
                                # TODO: Add a check for tasks belonging to the current user if this still doesn't narrow it down
                        except:
                            pass

        return context

    def _find_context(self, tk, context, path):
        file_name = os.path.splitext(os.path.basename(path))[0]
        # SWC JR: This could get slow if there are a lot of tasks, not sure if there is a way to query instead
        tasks = context.sgtk.shotgun.find("Task", [["entity", "is", context.entity]], ['content'])
        match_length = len(file_name)
        new_context_id = None

        for task in tasks:
            task_content = task['content']
            new_length = len(file_name) - len(task_content)
            if f"_{task_content}" in file_name and new_length < match_length:
                # We found a matching task
                new_context_id = task['id']
                # This is the new best task
                match_length = new_length

        if new_context_id:
            context = tk.context_from_entity("Task", new_context_id)

        return context


    ################################################################################################
# Helper stuff


class EntityPreset(object):
    """
    Little struct that represents one of the tabs / presets in the
    Left hand side entity tree view
    """

    def __init__(self, name, entity_type, model, proxy_model, view, publish_filters):
        self.model = model
        self.proxy_model = proxy_model
        self.name = name
        self.view = view
        self.entity_type = entity_type
        self.publish_filters = publish_filters

class UIWaitThread(QThread):
    def __init__(self, check_ui_closed_callback, parent=None):
        super(UIWaitThread, self).__init__(parent)
        self.check_ui_closed_callback = check_ui_closed_callback

    def run(self):
        ui_is_open = True
        while ui_is_open:
            time.sleep(1)
            ui_is_open = self.check_ui_closed_callback()
            logger.debug("UI is open: {}".format(ui_is_open))
        logger.debug("UI is closed, Updating pending view")
        self.parent().update_pending_view_signal.emit()

class UIWaitThreadOLD(QThread):
    def __init__(self, check_ui_closed_callback, parent=None):
        super(UIWaitThread, self).__init__(parent)
        self.check_ui_closed_callback = check_ui_closed_callback

    def run(self):
        ui_is_open = True
        while ui_is_open:
            time.sleep(1)
            ui_is_open = self.check_ui_closed_callback()
            logger.debug("UI is open: {}".format(ui_is_open))
        # When the loop exits (UI is closed), emit a signal to update the UI
        logger.debug("UI is closed, Updating pending view")
        self.parent().update_pending_view_signal.emit()


class MyLineEdit(QLineEdit):
    customTextChanged = QtCore.Signal(str)

    def __init__(self, *args, **kwargs):
        super(MyLineEdit, self).__init__(*args, **kwargs)
        self._currentText = ""  # Initialize the text storage
        self.textChanged.connect(self.updateText)

    def updateText(self, text):
        self._currentText = text  # Update the stored text
        # logger.debug(">>>>>>>>>>  text is: {}".format(text))
        self.customTextChanged.emit(text)  # Emit the custom signal with the updated text

    def get_current_text(self):
        # logger.debug(">>>>>>>>>>  self._currentText is: {}".format(self._currentText))
        return self._currentText  # Accessor method to get the stored text


class ShotGridLogHandlerOld(logging.Handler):
    def __init__(self, log_window):
        super().__init__()
        self.log_window = log_window
        self.log_queue = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.flush)
        self.timer.start(100)  # Update log window every 100ms

    def is_debug_logging_disabled(self):
        # find if shotgrid debug logging is disabled
        return False

    def emit(self, record):
        if record.levelno == logging.DEBUG and self.is_debug_logging_disabled():
            return  # Skip debug logs if debug logging is enabled

        msg = self.format(record)
        color = self.get_color(record.levelno)
        formatted_msg = f'<span style="color: {color};">{msg}</span><br>'
        self.log_queue.append(formatted_msg)

    def flush(self):
        if self.log_queue:
            self.log_window.append(''.join(self.log_queue))
            self.log_queue = []
            self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())
            QCoreApplication.processEvents()


    def get_color(self, levelno):
        if levelno == logging.DEBUG:
            return '#A9A9A9'  # Dark Grey
        elif levelno == logging.INFO:
            return '#D3D3D3'  # Light Grey
        elif levelno == logging.WARNING:
            return '#FFD700'  # Dark Yellow
        elif levelno == logging.ERROR:
            #return '#B22222'  # Dark Red
            return '#d45239'  # Red
        elif levelno == logging.CRITICAL:
            return '#FF8C00'  # Dark Orange
        return '#A9A9A9'  # Dark Grey

class ShotGridLogHandlerOriginal(logging.Handler):
    def __init__(self, log_window):
        super().__init__()
        self.log_window = log_window
        self.log_queue = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.flush)
        self.timer.start(100)  # Update log window every 100ms

    def is_debug_logging_disabled(self):
        # find if shotgrid debug logging is disabled
        return False
    def emit(self, record):
        #if record.levelno == logging.DEBUG and self.is_debug_logging_disabled():
        #    return  # Skip debug logs if debug logging is enabled

        msg = self.format(record)
        color = self.get_color(record.levelno)
        formatted_msg = f'<span style="color: {color};">{msg}</span><br>'
        self.log_queue.append(formatted_msg)

    def flush(self):
        if self.log_queue:
            self.log_window.append(''.join(self.log_queue))
            self.log_queue = []
            self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())
            QCoreApplication.processEvents()

    def get_color(self, levelno):
        if levelno == logging.DEBUG:
            return '#A9A9A9'  # Dark Grey
        elif levelno == logging.INFO:
            return '#D3D3D3'  # Light Grey
        elif levelno == logging.WARNING:
            return '#FFD700'  # Dark Yellow
        elif levelno == logging.ERROR:
            # return '#B22222'  # Dark Red
            return '#d45239'  # Red
        elif levelno == logging.CRITICAL:
            return '#FF8C00'  # Dark Orange
        return '#A9A9A9'  # Dark Grey

import logging
import os
#from PySide2.QtCore import QTimer, QCoreApplication

class ShotGridLogHandler(logging.Handler):
    def __init__(self, log_window):
        super().__init__()
        self.log_window = log_window
        self.log_queue = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.flush)
        self.timer.start(100)  # Update log window every 100ms

    def is_debug_logging_disabled(self):
        # ShotGrid uses the SGTK_DEBUG environment variable for debug logging
        debug_env = os.environ.get("SGTK_DEBUG", "0").lower()
        return debug_env in ("0", "false", "no", "")

    def emit(self, record):
        if record.levelno == logging.DEBUG and self.is_debug_logging_disabled():
            return  # Skip debug logs if debug logging is disabled
        msg = self.format(record)
        color = self.get_color(record.levelno)
        formatted_msg = f'<span style="color: {color};">{msg}</span><br>'
        self.log_queue.append(formatted_msg)

    def flush(self):
        if self.log_queue:
            self.log_window.append(''.join(self.log_queue))
            self.log_queue = []
            self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())
            QCoreApplication.processEvents()

    def get_color(self, levelno):
        if levelno == logging.DEBUG:
            return '#A9A9A9'  # Dark Grey
        elif levelno == logging.INFO:
            return '#D3D3D3'  # Light Grey
        elif levelno == logging.WARNING:
            return '#FFD700'  # Dark Yellow
        elif levelno == logging.ERROR:
            return '#d45239'  # Red
        elif levelno == logging.CRITICAL:
            return '#FF8C00'  # Dark Orange
        return '#A9A9A9'  # Default: Dark Grey

"""
import sgtk
import logging
from sgtk.platform.qt import QtCore, QtGui

# Assuming QTimer, QCoreApplication are imported elsewhere or available globally
# from sgtk.platform.qt import QtCore
# from sgtk.platform.qt import QtGui
# QTimer = QtCore.QTimer
# QCoreApplication = QtCore.QCoreApplication

class ShotGridLogHandler2(logging.Handler):
    def __init__(self, log_window):
        super().__init__()
        self.log_window = log_window
        self.log_queue = []
        self.timer = QtCore.QTimer() # Use QtCore explicitly if not globally imported
        self.timer.timeout.connect(self.flush)
        self.timer.start(100)  # Update log window every 100ms
        self._log_manager = sgtk.LogManager() # Get an instance of the LogManager

    def is_debug_logging_disabled(self):
        #Checks if ShotGrid debug logging is disabled.
        # Access the class property 'debug_logging_enabled' directly from sgtk.LogManager
        # It's a property, not a method, so no parentheses are needed.
        # return not self._log_manager.is_debug_logging_enabled() # Incorrect line from traceback
        return not sgtk.LogManager.debug_logging_enabled

    def emit(self, record):
        # Check if the record level is DEBUG and if debug logging is disabled
        if record.levelno == logging.DEBUG and self.is_debug_logging_disabled():
            return  # Skip debug logs if debug logging is disabled

        try:
            msg = self.format(record)
            color = self.get_color(record.levelno)
            # Ensure msg is properly escaped for HTML if necessary, though format usually handles it.
            # For simplicity, assuming format handles basic escaping.
            formatted_msg = f'<span style="color: {color};">{msg}</span><br>'
            self.log_queue.append(formatted_msg)
        except Exception:
            # Handle potential formatting errors gracefully
            self.handleError(record)


    def flush(self):
        # This method seems fine, but ensure thread safety if accessed from multiple threads.
        # For typical Qt GUI usage where logging happens from the main thread, it's likely okay.
        if self.log_queue:
            try:
                # Join the queued messages and append them
                messages_to_append = ''.join(self.log_queue)
                self.log_window.append(messages_to_append)
                self.log_queue = [] # Clear the queue

                # Scroll to the bottom
                scrollbar = self.log_window.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())

                # Process events to update the UI
                QtCore.QCoreApplication.processEvents()
            except Exception as e:
                # Basic error handling for flushing issues
                print(f"Error flushing log handler: {e}")


    def get_color(self, levelno):
        # This method seems fine
        if levelno >= logging.CRITICAL: # Use >= for CRITICAL and above
            return '#FF8C00'  # Dark Orange
        elif levelno >= logging.ERROR: # Use >= for ERROR and CRITICAL
            return '#d45239'  # Red
        elif levelno >= logging.WARNING: # Use >= for WARNING, ERROR, CRITICAL
            return '#FFD700'  # Dark Yellow
        elif levelno >= logging.INFO: # Use >= for INFO and above
            return '#D3D3D3'  # Light Grey
        elif levelno >= logging.DEBUG: # Use >= for DEBUG and above
             return '#A9A9A9'  # Dark Grey
        # Default or NOTSET level
        return '#A9A9A9' # Dark Grey (or choose another default)


import logging
from PySide2.QtCore import QTimer, QCoreApplication
from tank_vendor.shotgun_api3 import Shotgun

class ShotGridLogHandler(logging.Handler):
    def __init__(self, log_window):
        super().__init__()
        self.log_window = log_window
        self.log_queue = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.flush)
        self.timer.start(100)  # Update log window every 100ms

    def is_debug_logging_disabled(self):
        # Check if ShotGrid debug logging is disabled
        try:
            # Access ShotGrid's configuration via the API or environment
            # Assuming we're using the ShotGrid Python API
            sg = Shotgun()  # Initialize with appropriate credentials
            debug_logging = sg.get_debug_logging_status()  # Hypothetical method
            return not debug_logging
        except Exception:
            # Fallback to environment variable or config file check
            import os
            return os.getenv("SHOTGUN_DEBUG_LOGGING", "0") == "0"

    def emit(self, record):
        # Skip debug logs if debug logging is disabled
        if record.levelno == logging.DEBUG and self.is_debug_logging_disabled():
            return
        msg = self.format(record)
        color = self.get_color(record.levelno)
        formatted_msg = f'<span style="color: {color};">{msg}</span><br>'
        self.log_queue.append(formatted_msg)

    def flush(self):
        if self.log_queue:
            self.log_window.append(''.join(self.log_queue))
            self.log_queue = []
            self.log_window.verticalScrollBar().setValue(self.log_window.verticalScrollBar().maximum())
            QCoreApplication.processEvents()

    def get_color(self, levelno):
        if levelno == logging.DEBUG:
            return '#A9A9A9'  # Dark Grey
        elif levelno == logging.INFO:
            return '#D3D3D3'  # Light Grey
        elif levelno == logging.WARNING:
            return '#FFD700'  # Dark Yellow
        elif levelno == logging.ERROR:
            return '#d45239'  # Red
        elif levelno == logging.CRITICAL:
            return '#FF8C00'  # Dark Orange
        return '#A9A9A9'  # Dark Grey
"""
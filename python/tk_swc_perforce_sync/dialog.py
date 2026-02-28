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
import re


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
from .utils import resolve_filters, local_to_depot
from .utils import Icons

from .utils import check_validity_by_path_parts, check_validity_by_published_file


from . import constants
from . import model_item_data

from .ui.dialog import Ui_Dialog
from .publish_item import PublishItem

from .publish_files_ui import PublishFilesUI
from .perforce_sync_manager import PerforceSyncManager
from .view_manager import ViewManager
from .publish_integration import PublishIntegration
from .entity_browser import EntityBrowser

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
        self.repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

        #################################################
        # Perforce
        self._fw = sgtk.platform.get_framework("tk-framework-perforce")
        # PerforceSyncManager owns the P4 connection and all sync operations.
        self._sync_manager = PerforceSyncManager(self._app, self._fw, parent=self)
        self._sync_manager.log_message.connect(self._add_log)
        self._sync_manager.progress_update.connect(self._update_progress)
        self._sync_manager.sync_completed.connect(self._after_syncing_operations)
        self._sync_manager.sync_info.connect(self._on_sync_info)
        self._sync_manager.clobber_prompt.connect(self._on_clobber_prompt)
        self.ui.cancel_sync.clicked.connect(self._on_cancel_sync)
        # Compatibility alias — other code still references self._p4 directly.
        # These will be migrated to manager access in subsequent extraction steps.
        self._p4 = self._sync_manager.p4
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
        # details pane, view mode buttons, refresh/submit — wired after ViewManager creation below

        self.ui.refresh_button.clicked.connect(self._refresh_all)
        self.ui.get_latest_button.clicked.connect(self._get_latest)
        self.ui.submit_button.clicked.connect(self._submit_pending)

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

        # Playback button will be wired to ViewManager after its creation below

        # set up right click menu for the main publish view
        self._refresh_file_history_action = QAction("Refresh", self.ui.file_history_view)
        self._refresh_file_history_action.triggered.connect(
            self._publish_file_history_model.async_refresh
        )
        self.ui.file_history_view.addAction(self._refresh_file_history_action)
        self.ui.file_history_view.setContextMenuPolicy(Qt.ActionsContextMenu)

        # Set sync of file history
        self._sync_file_history_action = QAction("Sync", self.ui.file_history_view)
        self._sync_file_history_action.triggered.connect(self._on_sync_file_history)
        self.ui.file_history_view.addAction(self._sync_file_history_action)
        self.ui.file_history_view.setContextMenuPolicy(Qt.ActionsContextMenu)
        ###########################################

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

        # Signal connections for overlay are wired in ViewManager block below

        # hook up view -> proxy model -> model
        self.ui.publish_view.setModel(self._publish_proxy_model)

        # set up custom delegates to use when drawing the main area
        self._publish_thumb_delegate = SgPublishThumbDelegate(
            self.ui.publish_view, self._action_manager
        )

        self._publish_list_delegate = SgPublishListDelegate(
            self.ui.publish_view, self._action_manager
        )

        #################################################
        # ViewManager — owns view mode switching, column view, details pane,
        # publish view interaction, and filtering.
        self._view_manager = ViewManager(
            self._app, self.ui, self._settings_manager, self._action_manager,
            self._publish_model, self._publish_proxy_model, self._status_model,
            self._publish_file_history_model, self._publish_type_model,
            self.actions_icons, self._dynamic_widgets, parent=self
        )
        self._view_manager.log_message.connect(self._add_log)
        self._view_manager.column_view_action_requested.connect(self._on_column_view_action)
        # Provide delegates and pixmaps to view manager
        self._view_manager.set_delegates(self._publish_list_delegate, self._publish_thumb_delegate)
        self._view_manager.set_pixmaps(
            QPixmap(":/res/no_item_selected_512x400.png"),
            QPixmap(":/res/multiple_publishes_512x400.png"),
            QPixmap(":/res/no_publishes_found.png")
        )
        self._view_manager.set_publish_main_overlay(self._publish_main_overlay)
        self._view_manager.set_p4_and_helpers(
            self._p4, self._create_key, self._convert_local_to_depot
        )
        self._view_manager.set_get_entity_path_fn(self._get_entity_path)
        # Compatibility aliases for code that still references these on self
        self.main_view_mode = self._view_manager.main_view_mode
        self.column_view_model = self._view_manager.column_view_model
        self.perforce_proxy_model = self._view_manager.perforce_proxy_model

        # Wire view mode buttons to ViewManager
        self.ui.info.clicked.connect(self._view_manager.toggle_details_pane)
        self.ui.thumbnail_mode.clicked.connect(self._view_manager.on_thumbnail_mode_clicked)
        self.ui.list_mode.clicked.connect(self._view_manager.on_list_mode_clicked)
        self.ui.column_mode.clicked.connect(self._view_manager.on_column_mode_clicked)
        self.ui.submitted_mode.clicked.connect(self._on_submitted_mode_clicked)
        self.ui.pending_mode.clicked.connect(self._on_pending_mode_clicked)
        self.ui.file_detail_playback_btn.clicked.connect(
            self._view_manager.on_detail_version_playback
        )

        # Set initial view mode
        self._view_manager.set_main_view_mode(ViewManager.MAIN_VIEW_THUMB)

        # Publish type filter
        self._publish_type_model.itemChanged.connect(
            self._view_manager.apply_type_filters_on_publishes
        )

        # Publish view double-click
        self.ui.publish_view.doubleClicked.connect(self._on_publish_double_clicked)

        # Publish view selection
        self.ui.publish_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._publish_view_selection_model = self.ui.publish_view.selectionModel()
        self._publish_view_selection_model.selectionChanged.connect(
            self._on_publish_selection
        )

        # Publish model content change
        self._publish_model.cache_loaded.connect(self._view_manager.on_publish_content_change)
        self._publish_model.data_refreshed.connect(self._view_manager.on_publish_content_change)
        self._publish_proxy_model.filter_changed.connect(self._view_manager.on_publish_content_change)

        # Right click menu for the main publish view
        self._fix_action = QAction("Fix", self.ui.publish_view)
        self._fix_action.triggered.connect(lambda: self._on_publish_model_action("fix"))

        self._add_action = QAction("Add", self.ui.publish_view)
        self._add_action.triggered.connect(lambda: self._on_publish_model_action("add"))
        self._edit_action = QAction("Edit", self.ui.publish_view)
        self._edit_action.triggered.connect(lambda: self._on_publish_model_action("edit"))
        self._delete_action = QAction("Delete", self.ui.publish_view)
        self._delete_action.triggered.connect(lambda: self._on_publish_model_action("delete"))
        self._change_lists = QAction("1001", self._delete_action)
        self._change_lists.triggered.connect(lambda: self._on_publish_model_action("1001"))
        self._revert_action = QAction("Revert", self.ui.publish_view)
        self._revert_action.triggered.connect(lambda: self._on_publish_model_action("revert"))
        self._sync_action = QAction("Sync", self.ui.publish_view)
        self._sync_action.triggered.connect(lambda: self._on_publish_model_action("sync"))
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
        self._search_widget = SearchWidget(self.ui.publish_frame)
        self._view_manager.set_search_widget(self._search_widget)
        self.ui.search_publishes.clicked.connect(self._view_manager.on_publish_filter_clicked)
        self._search_widget.filter_changed.connect(
            self._publish_proxy_model.set_search_query
        )
        self._search_widget.filter_changed.connect(
            self._view_manager.on_column_view_set_search_query
        )

        #################################################
        # checkboxes, buttons etc
        self.ui.sync_files.clicked.connect(self._on_sync_files)
        self.ui.sync_parents.clicked.connect(self._on_sync_parents)

        self.ui.check_all.clicked.connect(self._publish_type_model.select_all)
        self.ui.check_none.clicked.connect(self._publish_type_model.select_none)

        #################################################
        # thumb scaling
        scale_val = self._settings_manager.retrieve("thumb_size_scale", 140)
        self.ui.thumb_scale.setValue(scale_val)
        self.ui.publish_view.setIconSize(QSize(scale_val, scale_val))
        self.ui.thumb_scale.valueChanged.connect(self._view_manager.on_thumb_size_slider_change)

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
        # PublishIntegration — owns publishing workflows, pending/submitted views,
        # changelist operations, CLI submission, fix operations.
        self._publish_integration = PublishIntegration(
            self._app, self.ui, self._sync_manager, parent=self
        )
        self._publish_integration.log_message.connect(self._add_log)
        self._publish_integration.set_publish_model(self._publish_model, SgLatestPublishModel)
        self._publish_integration.set_callbacks(
            get_selected_entity_fn=self._get_selected_entity,
            load_publishes_for_entity_item_fn=self._load_publishes_for_entity_item,
            get_entity_info_fn=self._get_entity_info,
            create_key_fn=self._create_key,
            convert_local_to_depot_fn=self._convert_local_to_depot,
            add_log_fn=self._add_log,
            reload_treeview_fn=lambda: self._reload_treeview(),
            on_treeview_item_selected_fn=lambda: self._on_treeview_item_selected(),
            setup_file_details_panel_fn=lambda items: self._setup_file_details_panel(items),
            do_sync_files_fn=lambda files: self._sync_manager.sync_files_list(files),
            refresh_publish_data_fn=lambda: self.refresh_publish_data(),
        )
        # Compatibility aliases
        self._sg_data = self._publish_integration._sg_data
        self._fstat_dict = self._publish_integration._fstat_dict
        self._change_dict = self._publish_integration._change_dict
        self._submitted_data_to_publish = self._publish_integration._submitted_data_to_publish
        self._pending_data_to_publish = self._publish_integration._pending_data_to_publish
        self._action_data_to_publish = self._publish_integration._action_data_to_publish
        self.publish_files_ui = PublishFilesUI(self, self.window())

        # Wire buttons that depend on _publish_integration
        self.ui.fix_selected.clicked.connect(self._publish_integration.on_fix_selected)
        self.ui.fix_all.clicked.connect(self._publish_integration.on_fix_all)
        self.ui.submit_files.clicked.connect(self._publish_integration._on_submit_files)

        #################################################
        # EntityBrowser — owns entity detail panels, parent/children,
        # breadcrumbs, entity path resolution, filesystem operations.
        self._entity_browser = EntityBrowser(
            self._app, self.ui, self._sync_manager, parent=self
        )
        self._entity_browser.log_message.connect(self._add_log)

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
        self.action_dict = constants.ACTION_MAP
        self.status_dict = constants.STATUS_MAP
        self.settings = constants.EXTENSION_TYPE_MAP
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
        # Schedule refresh_entity_preset_tabs to run after a 5-second delay
        # This allows initial UI setup and asynchronous data loading (e.g., P4 connection,
        # initial model loads) to progress before attempting this potentially heavy refresh.
        initial_refresh_delay_ms = 5000  # 5 seconds
        QtCore.QTimer.singleShot(initial_refresh_delay_ms, self.refresh_entity_preset_tabs)
        logger.debug(
            f"Scheduled a delayed call to refresh_entity_preset_tabs in {initial_refresh_delay_ms / 1000} seconds."
        )
        #################################################

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

    def _get_shotgun_panel_widget(self, target_entity=None):
        """
        Retrieves or creates the Shotgun Panel widget and navigates it
        to the specified target entity.

        :param dict target_entity: The ShotGrid entity dictionary (e.g., Asset, Shot)
                                   to navigate the panel to. If None, attempts
                                   to use self._entity_data.
        """
        engine = sgtk.platform.current_engine()
        if not engine:
            logger.error("No current engine found.")
            return  # Return early if no engine

        shotgun_panel_app = engine.apps.get("tk-multi-shotgunpanel")

        if shotgun_panel_app:
            try:
                # Get or create the widget
                if not self.shotgun_panel_widget:
                    # Pass the parent widget (self.ui.panel_details)
                    self.shotgun_panel_widget = shotgun_panel_app.create_widget(self.ui.panel_details)

                if self.shotgun_panel_widget:
                    # --- Navigation Logic ---
                    # Prioritize the explicitly passed target_entity
                    entity_to_navigate = target_entity if target_entity else self._entity_data

                    if entity_to_navigate:
                        # Extract ID and Type directly from the resolved entity
                        entity_id = entity_to_navigate.get("id")
                        entity_type = entity_to_navigate.get("type")

                        if entity_id and entity_type:
                            logger.debug(f"Navigate to entity: {entity_type} ID # {entity_id}")
                            try:
                                # Ensure navigation happens after widget is potentially created/added
                                QtCore.QTimer.singleShot(0, lambda: self.shotgun_panel_widget.navigate_to_entity(
                                    entity_type, entity_id))
                                # self.shotgun_panel_widget.navigate_to_entity(entity_type, entity_id) # Original direct call
                            except Exception as nav_err:
                                logger.error(f"Error during panel navigation: {nav_err}")
                        else:
                            logger.warning(
                                f"Could not navigate panel: Invalid ID ({entity_id}) or Type ({entity_type}) in {entity_to_navigate}")
                    else:
                        logger.debug("No entity data available for panel navigation.")
                    # --- End Navigation Logic ---

                    # --- Layout Logic ---
                    # Check if the widget is already in the layout to avoid adding duplicates
                    current_widget = self.ui.panel_layout.itemAt(0)
                    if not current_widget or current_widget.widget() != self.shotgun_panel_widget:
                        # Clear existing widgets first
                        while self.ui.panel_layout.count():
                            child = self.ui.panel_layout.takeAt(0)
                            if child.widget():
                                # Set parent to None to remove without deleting immediately
                                child.widget().setParent(None)

                        # Add the panel widget
                        self.ui.panel_layout.addWidget(self.shotgun_panel_widget)
                        logger.info("Shotgun panel widget added/updated in the layout.")
                    # --- End Layout Logic ---

                else:
                    logger.error("Failed to retrieve or create the panel widget.")
            except Exception as e:
                logger.error(f"Failed to create or add the Shotgun panel widget: {e}", exc_info=True)
        else:
            logger.warning("Shotgun Panel app 'tk-multi-shotgunpanel' is not loaded.")



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
                        menu.addAction(self._sync_action)
                        menu.addSeparator()
                        menu.addAction(self._refresh_action)
                    else:
                        menu.addAction(self._fix_action)
                        menu.addSeparator()
                        menu.addAction(self._revert_action)
                        menu.addSeparator()
                        menu.addAction(self._sync_action)
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
    def _get_default_change(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_default_change()

    def _get_default_changelists(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._get_default_changelists()
        self._change_dict = self._publish_integration._change_dict

    def get_client_name(self):
        return self._sync_manager.get_client_name()

    def get_change_lists(self, workspace):
        return self._sync_manager.get_change_lists(workspace)

    def get_desc_files(self, key):
        return self._sync_manager.get_desc_files(key)

    def get_fstat_list(self, depot_file):
        return self._sync_manager.get_fstat_list(depot_file)

    def _get_pending_changelists(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._get_pending_changelists()
        self._change_dict = self._publish_integration._change_dict

    def _get_client_file(self, depot_file):
        return self._sync_manager.get_client_file(depot_file)

    def _get_pending_publish_data(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._get_pending_publish_data()

    def _get_submitted_publish_data(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._get_submitted_publish_data()

    def _create_perforce_ui(self, data_dict, sorted=None):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._create_perforce_ui(data_dict, sorted)

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
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._create_publish_layout(data_dict, sorted)

    def _get_change_list_info(self, sg_item):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_change_list_info(sg_item)

    def _get_publish_time_info(self, sg_item):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_publish_time_info(sg_item)

    def _get_user_name_info(self, sg_item):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_user_name_info(sg_item)

    def _get_description_info(self, sg_item):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_description_info(sg_item)

    def _get_publish_time(self, sg_item):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_publish_time(sg_item)

    def _get_publish_user(self, sg_item):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_publish_user(sg_item)

    def _get_change_dictionary(self, data_dict):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_change_dictionary(data_dict)

    def _get_action(self, sg_item):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_action(sg_item)

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

    # _on_column_view_set_search_query and _on_publish_filter_clicked
    # are now wired directly to ViewManager in __init__


    def _on_submitted_mode_clicked(self):
        """Handles submitted mode: sets view mode then populates widget."""
        self._view_manager.set_main_view_mode(ViewManager.MAIN_VIEW_SUBMITTED)
        self.main_view_mode = self._view_manager.main_view_mode
        self._populate_submitted_widget()

    def _on_pending_mode_clicked(self):
        """Handles pending mode: sets view mode then populates widget."""
        self._view_manager.set_main_view_mode(ViewManager.MAIN_VIEW_PENDING)
        self.main_view_mode = self._view_manager.main_view_mode
        self._populate_pending_widget()

    def _set_main_view_mode(self, mode):
        """Compatibility wrapper — delegates to ViewManager."""
        self._view_manager.set_main_view_mode(mode)
        self.main_view_mode = self._view_manager.main_view_mode
        # For submitted/pending, also populate the widget
        if mode == self.MAIN_VIEW_SUBMITTED:
            self._populate_submitted_widget()
        elif mode == self.MAIN_VIEW_PENDING:
            self._populate_pending_widget()

    def _populate_pending_widget(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.populate_pending_widget()

    def _refresh_all(self):
        mode = self._view_manager.main_view_mode
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
        #msg = "\n <span style='color:#2C93E2'>Refreshing type model ...</span> \n"
        #self._add_log(msg, 2)
        #self._publish_type_model.hard_refresh()
        #msg = "\n <span style='color:#2C93E2'>Refreshing publish model ...</span> \n"
        #self._add_log(msg, 2)
        #self._publish_model.hard_refresh()

        msg = "\n <span style='color:#2C93E2'>Refresh entity presets and sync count ...</span> \n"
        self._add_log(msg, 2)
        # for p in self._entity_presets:
        #    self._entity_presets[p].model.hard_refresh()
        self.refresh_entity_preset_tabs()

        msg = "\n <span style='color:#2C93E2'>Reloading view for current selection...</span> \n"
        self._add_log(msg, 2)
        # self._on_home_clicked()
        self._on_treeview_item_selected()
        #self._load_entity_presets()
        #self._recreate_entity_presets()


    def _refresh_column_view(self):
        self._refresh_publish_area()
        msg = "\n <span style='color:#2C93E2'>Refreshing Column view ...</span> \n"
        self._add_log(msg, 2)
        self._view_manager.populate_column_view_widget()

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
                        msg = "{} files".format(sync_count)

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

    def _on_sync_current(self):
        """
        Finds the currently selected entity, determines its Perforce depot path,
        and syncs the files within that path that need updating.
        """
        entity_path, entity_id, entity_type = self._get_selected_entity_path_info()
        self._sync_manager.sync_current_entity(entity_path)



    def _on_sync_file_history(self):
        """
        Syncs the specific version of the file currently selected in the
        file history view.
        """
        logger.debug("Attempting to sync selected file from history...")

        # Get the selected item from the file history view
        selection_model = self.ui.file_history_view.selectionModel()
        if not selection_model.hasSelection():
            logger.info("No item selected in file history to sync.")
            self._add_log("\n <span style='color:#FFD700'>No file version selected in the history panel.</span> \n",
                          2)
            return

        # Assuming single selection for simplicity, take the first selected index
        selected_indexes = selection_model.selectedIndexes()
        if not selected_indexes:
            return  # Should be redundant given hasSelection(), but good practice

        proxy_index = selected_indexes[0]
        # Ensure you are using the correct proxy model for the file history view
        source_index = self._publish_file_history_proxy.mapToSource(proxy_index)
        item = self._publish_file_history_model.itemFromIndex(source_index)

        if not item:
            logger.error("Could not retrieve item from file history selection.")
            self._add_log(
                "\n <span style='color:#CC3333'>Error: Could not retrieve selected history item.</span> \n", 2)
            return

        sg_data = item.get_sg_data()  # This should be the PublishedFile data for that specific version
        if not sg_data:
            logger.error("No ShotGrid data associated with the selected file history item.")
            self._add_log(
                "\n <span style='color:#CC3333'>Error: No data found for selected history item.</span> \n", 2)
            return

        file_name_display = sg_data.get("name", sg_data.get("code", "Unknown file"))
        version_number = sg_data.get("version_number")
        depot_path = sg_data.get("sg_p4_depo_path")

        if not depot_path:
            # Try to derive from local_path if sg_p4_depo_path is missing
            local_path = sg_data.get("path", {}).get("local_path")
            if local_path:
                depot_path = self._convert_local_to_depot(local_path)  # Ensure this helper exists
                if not depot_path:  # If conversion failed
                    logger.error(
                        f"Cannot sync '{file_name_display}': Failed to convert local path '{local_path}' to depot path.")
                    self._add_log(
                        f"\n <span style='color:#CC3333'>Error: Could not determine Perforce path for '{file_name_display}'.</span> \n",
                        2)
                    return
            else:
                logger.error(
                    f"Cannot sync '{file_name_display}': Missing Perforce depot path and local path information.")
                self._add_log(
                    f"\n <span style='color:#CC3333'>Error: Path information missing for '{file_name_display}'.</span> \n",
                    2)
                return

        if version_number is None:  # version_number could be 0, so check for None
            logger.error(f"Cannot sync '{file_name_display}': Version number is missing from history item.")
            self._add_log(
                f"\n <span style='color:#CC3333'>Error: Version number missing for '{file_name_display}'.</span> \n",
                2)
            return

        # Construct the Perforce path with revision specifier (e.g., //depot/file.ma#5)
        depot_path_with_revision = f"{depot_path}#{version_number}"

        logger.info(f"Preparing to sync specific version: {depot_path_with_revision}")
        self._add_log(
            f"\n <span style='color:#2C93E2'>Syncing: {os.path.basename(depot_path)} (Version {version_number})</span> \n",
            2)
        self._add_log(f"  Depot path: {depot_path_with_revision}", 3)

        try:
            if not self._p4 or not self._p4.connected():
                logger.warning("Perforce not connected. Attempting to connect...")
                self._connect_P4()
                if not self._p4 or not self._p4.connected():
                    logger.error("Failed to connect to Perforce. Sync aborted.")
                    self._add_log("\n <span style='color:#CC3333'>Error: Failed to connect to Perforce.</span> \n",
                                  2)
                    return

            # Perform the sync for the specific file and version
            sync_result = self._p4.run_sync(depot_path_with_revision)

            if sync_result is False or sync_result is None:
                logger.error(f"Perforce sync command failed for {depot_path_with_revision}. Result: {sync_result}")
                self._add_log(
                    f"\n <span style='color:#CC3333'>Error syncing {file_name_display} v{version_number}. Check Perforce logs.</span> \n",
                    2)
            elif isinstance(sync_result, list):
                if not sync_result:
                    logger.info(f"File {depot_path_with_revision} is already up to date.")
                    self._add_log(
                        f"\n <span style='color:#2C93E2'>{file_name_display} v{version_number} is already up to date.</span> \n",
                        2)
                else:
                    synced_file_info = "Synced: "
                    for entry in sync_result:
                        if isinstance(entry, dict):
                            action = entry.get("action", "updated")
                            client_file = entry.get("clientFile", depot_path)  # Fallback to depot_path for display
                            synced_file_info += f"{os.path.basename(client_file)} ({action}), "
                    synced_file_info = synced_file_info.rstrip(", ")
                    logger.info(f"Successfully synced {depot_path_with_revision}.")
                    self._add_log(
                        f"\n <span style='color:#2C93E2'>Successfully {synced_file_info} (Version {version_number}).</span> \n",
                        2)

                # Refresh relevant data after a successful or "already up-to-date" sync
                # Use QTimer.singleShot to ensure it runs after current event processing
                QtCore.QTimer.singleShot(0, self._after_syncing_operations)
            else:
                logger.warning(f"Unexpected result from p4.run_sync for {depot_path_with_revision}: {sync_result}")
                self._add_log(
                    f"\n <span style='color:#FFD700'>Sync status unclear for {file_name_display} v{version_number}.</span> \n",
                    2)

        except Exception as e:
            logger.error(f"Exception during sync of {depot_path_with_revision}: {e}", exc_info=True)
            self._add_log(
                f"\n <span style='color:#CC3333'>Exception syncing {file_name_display} v{version_number}: {e}</span> \n",
                2)

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
                        msg = "{} files".format(sync_count)

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
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._create_pending_view_context_menu()

    def _show_pending_view_actions(self, pos):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._show_pending_view_actions(pos)

    def _list_files_in_changelist(self, change):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._list_files_in_changelist(change)

    def _validate_changelist_files(self, files_in_changelist):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._validate_changelist_files(files_in_changelist)

    def _on_pending_view_model_action(self, action):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._on_pending_view_model_action(action)

    def _validate_changelist_files_with_threads(self, files_in_changelist):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._validate_changelist_files_with_threads(files_in_changelist)

    def _after_publish_ui_close(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._after_publish_ui_close()

    def check_publisher_ui_closed(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.check_publisher_ui_closed()

    def _wait_for_ui_close(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._wait_for_ui_close()

    def _check_ui_closed(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._check_ui_closed()

    def _create_description_file(self, files_in_changelist, description):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._create_description_file(files_in_changelist, description)

    def _delete_pending_file(self, change, target_file):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._delete_pending_file(change, target_file)

    def _get_pending_data_from_source(self, source_index):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_pending_data_from_source(source_index)

    def _get_action_data_from_source(self, source_index):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_action_data_from_source(source_index)

    def _get_change_data_from_source(self, source_index):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_change_data_from_source(source_index)

    def _get_sg_data_from_source(self, source_index):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_sg_data_from_source(source_index)

    def _get_pending_info_from_source(self, source_index):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_pending_info_from_source(source_index)

    def _populate_column_view_widget(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager.set_sg_data(self._sg_data)
        self._view_manager.set_item_path_dict(self._item_path_dict)
        self._view_manager.set_entity_path(self._entity_path)
        self._view_manager.populate_column_view_widget()
        # Update compatibility aliases
        self.column_view_model = self._view_manager.column_view_model
        self.perforce_proxy_model = self._view_manager.perforce_proxy_model

    def _setup_column_view(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager._setup_column_view()
        self.column_view_model = self._view_manager.column_view_model
        self.perforce_proxy_model = self._view_manager.perforce_proxy_model

    def _setup_file_details_panel(self, items):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager.setup_file_details_panel(items)

    def _setup_column_details_panel(self, id):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager._setup_column_details_panel(id)

    def _set_column_group(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager._set_column_group()

    def _turn_all_modes_off(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager._turn_all_modes_off()

    def _show_thumb_scale(self, is_visible):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager._show_thumb_scale(is_visible)

    def _toggle_details_pane(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager.toggle_details_pane()

    def _set_details_pane_visiblity(self, visible):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager.set_details_pane_visibility(visible)

    def _on_detail_version_playback(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager.on_detail_version_playback()

    def _on_publish_selection(self, selected, deselected):
        """Compatibility wrapper -- delegates to ViewManager then emits signal."""
        self._view_manager.on_publish_selection(selected, deselected)
        self.selection_changed.emit()

    def _on_publish_content_change(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager.on_publish_content_change()

    def _apply_type_filters_on_publishes(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager.apply_type_filters_on_publishes()

    def _on_thumb_size_slider_change(self, value):
        """Compatibility wrapper -- delegates to ViewManager."""
        self._view_manager.on_thumb_size_slider_change(value)

    def _get_entity_path(self, entity_data):
        """Get entity path for a given entity."""
        if not entity_data:
            return None
        entity_id = entity_data.get('id', 0)
        entity_type = entity_data.get('type', None)
        if entity_type == "Task":
            entity = entity_data.get("entity", None)
            if entity:
                entity_id = entity.get('id', entity_id)
                entity_type = entity.get('type', entity_type)
        entity_path = self._app.sgtk.paths_from_entity(entity_type, entity_id)
        return entity_path[-1] if entity_path else None

    def _path_difference(self, path1, path2):
        """Compatibility wrapper -- delegates to ViewManager."""
        from .view_manager import ViewManager as VM
        return VM._path_difference(path1, path2)

    def get_row_data_from_source(self, source_index):
        """Compatibility wrapper -- delegates to ViewManager."""
        return self._view_manager._get_row_data_from_source(source_index)

    def _set_column_view_mode(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        from .view_manager import ViewManager as VM
        self._view_manager.set_main_view_mode(VM.MAIN_VIEW_COLUMN)
        self.main_view_mode = self._view_manager.main_view_mode

    def _set_thump_view_mode(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        from .view_manager import ViewManager as VM
        self._view_manager.set_main_view_mode(VM.MAIN_VIEW_THUMB)
        self.main_view_mode = self._view_manager.main_view_mode

    def _on_column_view_action(self, action, action_data_list):
        """Routes column view actions to appropriate manager."""
        if not action_data_list:
            return
        data = action_data_list[0]
        selected_items = data.get("selected_items", [])
        files_to_revert = data.get("files_to_revert", [])
        files_to_sync = data.get("files_to_sync", [])

        if action == "revert" and files_to_revert:
            try:
                msg = f"Reverting {len(files_to_revert)} selected file(s)..."
                self._add_log(msg, 2)
                p4_result = self._p4.run("revert", *files_to_revert)
                logger.debug(f"Bulk revert result: {p4_result}")
                if p4_result:
                    self.refresh_publish_data()
            except Exception as e:
                logger.error(f"Error during bulk revert: {e}")
                self._add_log(f"Error during bulk revert: {e}", 2)

        if action == "sync" and files_to_sync:
            try:
                msg = f"Syncing {len(files_to_sync)} selected file(s)..."
                self._add_log(msg, 2)
                self._sync_manager.sync_files_list(files_to_sync)
            except Exception as e:
                logger.error(f"Error during bulk sync: {e}")
                self._add_log(f"Error during bulk sync: {e}", 2)

        if selected_items:
            self.perform_changelist_selection(selected_items)

    def _get_perforce_sg_data(self):
        """Compatibility wrapper -- delegates to ViewManager."""
        return self._view_manager._get_perforce_sg_data()

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
                        sg_item = shotgun_model.get_sg_data(model_index)
                        action = sg_item.get("action") or sg_item.get("headAction") or None
                        if action and action in ["delete"]:
                            model.removeRow(row)
                            is_model_changed = True
                if is_model_changed:
                    model.layoutChanged.emit()
                    self.ui.publish_view.update()
        except:
            pass


    def _populate_submitted_widget(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.populate_submitted_widget()

    def _reset_submitted_widget(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._reset_submitted_widget()

    def update_pending_view(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.update_pending_view()

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

    def _get_entity_parents(self, entity_data):
        """
        Get the entity parents for a given item.
        :param entity_data:
        :return:
        """
        self.entity_parents = self._sync_manager.get_entity_parents(entity_data, self._app)
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

    def _sync_entity_parents_published_files(self):
        """Sync the published files for the parents of the selected entity."""
        self._sync_manager.sync_entity_parents_published_files(self.entity_parents, self._app)

    def _sync_entity_children_published_files(self):
        """Sync the published files for the children of the selected entity."""
        self._sync_manager.sync_entity_children_published_files(self.entity_children, self._app)

    def _on_sync_entity_files(self):
        """Callback method when the sync entity files button is clicked."""
        self._sync_manager.sync_entity_files(self.entity_parents, self.entity_children, self._app)

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
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._on_submit_files()

    def _get_submit_changelist_widget_data(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_submit_changelist_widget_data()

    def _extract_file_info(self, target_file):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._extract_file_info(target_file)

    def _on_submit_changelist(self, submitter_widget):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._on_submit_changelist(submitter_widget)

    def on_submit_deleted_files(self, change_sg_item, file_info_deleted):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.on_submit_deleted_files(change_sg_item, file_info_deleted)

    def on_submit_other_files(self, change_sg_item, file_info_other):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.on_submit_other_files(change_sg_item, file_info_other)

    def _publish_file_thread(self, change, target_file, action, sg_item, log_callback, get_entity_callback):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._publish_file_thread(change, target_file, action, sg_item, log_callback, get_entity_callback)

    def _publish_pending_data_using_command_line(self, selected_tuples_to_publish):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._publish_pending_data_using_command_line(selected_tuples_to_publish)

    def get_entity_from_sg_item(self, sg_item):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration.get_entity_from_sg_item(sg_item)

    def _delete_file_thread(self, p4, change, file_to_submit, log_callback):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._delete_file_thread(p4, change, file_to_submit, log_callback)

    def _delete_pending_data(self, selected_tuples_to_delete):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._delete_pending_data(selected_tuples_to_delete)

    def _submit_other_pending_data(self, selected_data_to_submit):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._submit_other_pending_data(selected_data_to_submit)

    def _publish_other_pending_data(self, other_data_to_publish):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._publish_other_pending_data(other_data_to_publish)

    def _publish_delete_pending_data(self, deleted_data_to_publish):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._publish_delete_pending_data(deleted_data_to_publish)

    def _publish_deleted_data_using_command_line(self, deleted_data_to_publish):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._publish_deleted_data_using_command_line(deleted_data_to_publish)

    def _delete_one_file_thread(self, sg_item, file_path):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._delete_one_file_thread(sg_item, file_path)

    def _get_published_files(self, sg_item):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._get_published_files(sg_item)

    def _on_fix_list(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.on_fix_list()

    def _on_fix_selected(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.on_fix_selected()

    def _on_fix_all(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.on_fix_all()

    def _create_publisher_dir(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._create_publisher_dir()

    def _on_publish_files(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.on_publish_files()

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
        files_to_sync, total_file_count = self._get_files_to_sync()
        self._sync_manager.sync_files_list(files_to_sync)

    def _sync_entity_parents(self):
        logger.debug("Getting entity parents")
        self._get_entity_parents(self._entity_data)
        logger.debug("Syncing entity parents published files")
        self._sync_manager.sync_entity_parents_published_files(self.entity_parents, self._app)

    def _get_perforce_summary(self):
        self._sync_manager.get_perforce_summary(
            self.ui.publish_view.model(), shotgun_model, SgLatestPublishModel)


    ########################################################################################


    # Perforce connection, Sync, and related GUI items
    def _publish_submitted_data_using_publisher_ui(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._publish_submitted_data_using_publisher_ui()

    def _publish_submitted_data_using_command_line(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._publish_submitted_data_using_command_line()

    def _publish_one_file_thread(self, sg_item, file_to_publish, rev):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._publish_one_file_thread(sg_item, file_to_publish, rev)

    def _create_key(self, file_path):
        return PerforceSyncManager.create_key(file_path)

    def _get_files_to_sync(self):
        return self._sync_manager.get_files_to_sync(
            self.ui.publish_view.model(), shotgun_model, SgLatestPublishModel)

    def _update_progress(self, value):
        """
        Updates the progress bar with the given value, ensuring thread-safe UI updates.

        Args:
            value (float): Progress value between 0 and 100.
        """
        logger.debug("_update_progress received %.1f%%", value)
        if not hasattr(self, '_progress_updater'):
            self._progress_updater = ProgressUpdater(self.ui.progress, self)
        self._progress_updater.update_progress.emit(value)

    def _on_sync_info(self, file_count, size_str):
        """Called when sync provides file count and size info."""
        if file_count == 0 and size_str:
            # Dry-run in progress
            self.ui.sync_status_label.setText(size_str)
        elif size_str:
            self.ui.sync_status_label.setText(
                "Syncing {} files ({})...".format(file_count, size_str))
        else:
            self.ui.sync_status_label.setText(
                "Syncing {} files...".format(file_count))
        self.ui.sync_status_label.setVisible(True)
        self.ui.cancel_sync.setVisible(True)
        self.ui.cancel_sync.setEnabled(True)
        self.ui.progress.setRange(0, 100)
        self.ui.progress.setValue(0)
        self.ui.progress.setVisible(True)
        self.ui.sync_files.setEnabled(False)
        self.ui.sync_parents.setEnabled(False)
        self.ui.get_latest_button.setEnabled(False)

    def _on_cancel_sync(self):
        """Cancel the current sync operation."""
        self._sync_manager.cancel_sync()
        self.ui.sync_status_label.setText("Cancelling...")
        self.ui.cancel_sync.setEnabled(False)

    def _on_clobber_prompt(self, depot_files):
        """Prompt user before syncing writable files that P4 would refuse to overwrite."""
        count = len(depot_files)
        file_list = "\n".join(f.rsplit("/", 1)[-1] for f in depot_files[:20])
        if count > 20:
            file_list += "\n... and {} more".format(count - 20)

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Writable Files Detected")
        msg.setText(
            "{} file(s) are writable on disk but not checked out in Perforce.\n"
            "These files will be skipped unless you choose to overwrite them.".format(count))
        msg.setDetailedText(file_list)
        overwrite_btn = msg.addButton("Overwrite All", QMessageBox.AcceptRole)
        skip_btn = msg.addButton("Skip These", QMessageBox.RejectRole)
        cancel_btn = msg.addButton("Cancel Sync", QMessageBox.DestructiveRole)
        msg.exec_()

        clicked = msg.clickedButton()
        if clicked == cancel_btn:
            self._sync_manager.cancel_sync()
        elif clicked == overwrite_btn:
            self._add_log(
                "\n <span style='color:#2C93E2'>Overwriting {} writable file(s)...</span> \n".format(count), 2)
            self._sync_manager.respond_to_clobber(overwrite=True)
        else:
            self._add_log(
                "\n <span style='color:#FFD700'>Skipping {} writable file(s)...</span> \n".format(count), 2)
            self._sync_manager.respond_to_clobber(overwrite=False)

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
        """
        Adds a message to the log window, ensuring thread-safe UI updates.

        Args:
            msg (str): The log message to display.
            flag (int): The log level for formatting (1-2: add newlines, 3+: no newlines).
        """
        if not hasattr(self, '_log_updater'):
            self._log_updater = LogUpdater(self)
        self._log_updater.updateLog.emit(msg, flag)

    def _to_sync(self, have_rev, head_rev):
        return PerforceSyncManager.to_sync(have_rev, head_rev)

    def _connect(self):
        self._sync_manager.reconnect()
        self._p4 = self._sync_manager.p4
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
                        sync_msg = "Up to date" if sync_count == 0 else f"{sync_count} files"
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
        Loads entity presets from the configuration and sets up the UI for each tab.

        This version standardizes all tabs to include a "Name" and "To Sync" column,
        preparing them for asynchronous data loading.
        """
        app = sgtk.platform.current_bundle()

        # Disconnect the tab change signal while rebuilding to prevent errors
        try:
            self.ui.entity_preset_tabs.currentChanged.disconnect(
                self._on_entity_profile_tab_clicked
            )
        except (TypeError, RuntimeError):
            # Signal was not connected yet, which is fine on first run.
            pass

        # Clear existing presets and UI elements before rebuilding
        self._entity_presets = {}
        self.ui.entity_preset_tabs.clear()
        self._dynamic_widgets = []

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
            value = setting_dict.get(key, "Query")  # Default to Query
            if value not in ("Hierarchy", "Query"):
                raise TankError(value_error_msg % (setting_dict, key, value))
            type_hierarchy = value == "Hierarchy"

            sg_entity_type = None
            if type_hierarchy:
                key = "root"
                if key not in setting_dict:
                    raise TankError(key_error_msg % (setting_dict, key))
                sg_entity_type = "Project"
            else:  # Query type
                for key in ("entity_type", "hierarchy", "filters"):
                    if key not in setting_dict:
                        raise TankError(key_error_msg % (setting_dict, key))
                sg_entity_type = setting_dict["entity_type"]

            publish_filters = setting_dict.get("publish_filters", [])
            # --- End Validation ---

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

            # --- Setup View (Applied to ALL tabs for consistency) ---
            view.setEditTriggers(QAbstractItemView.NoEditTriggers)
            view.setProperty("showDropIndicator", False)
            view.setIconSize(QSize(20, 20))
            view.setStyleSheet("QTreeView::item { padding: 6px; }")
            view.setUniformRowHeights(True)

            # --- Standardize the two-column layout for all tabs ---
            view.setHeaderHidden(False)
            view.header().setStretchLastSection(False)
            view.header().setSectionResizeMode(0, QHeaderView.Stretch)
            view.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            view.setSortingEnabled(True)
            view.sortByColumn(0, Qt.AscendingOrder)

            source_model = proxy_model.sourceModel()
            # Ensure model has 2 columns for "Name" and "To Sync"
            if source_model.columnCount() < 2:
                source_model.setColumnCount(2)
            source_model.setHorizontalHeaderLabels(["Name", "To Sync"])
            # --- End of standardized setup ---

            # --- Search Widgets (logic remains the same) ---
            if not type_hierarchy:
                search_layout = QHBoxLayout()
                layout.addLayout(search_layout)

                search_edit = MyLineEdit(tab)
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
                search_edit.setPlaceholderText("Search...")
                search_layout.addWidget(search_edit)

                search_button = QPushButton("Search", tab)
                search_button.setToolTip("Click to search for items displayed in the tree above.")
                search_layout.addWidget(search_button)

                clear_search_button = QToolButton(tab)
                clear_icon = QIcon(":/res/clear_search.png")
                clear_search_button.setIcon(clear_icon)
                clear_search_button.setAutoRaise(True)
                clear_search_button.setToolTip("Click to clear your current search.")
                clear_search_button.clicked.connect(lambda checked=False, editor=search_edit: editor.setText(""))
                search_layout.addWidget(clear_search_button)

                search_edit.returnPressed.connect(
                    lambda v=view, pm=proxy_model, search=search_edit: self.trigger_search(v, pm, search)
                )
                search_button.clicked.connect(
                    lambda v=view, pm=proxy_model, search=search_edit: self.trigger_search(v, pm, search)
                )
                self._dynamic_widgets.extend([search_layout, search_edit, search_button, clear_search_button, clear_icon])
            else:  # Hierarchy model
                hierarchical_search = shotgun_search_widget.HierarchicalSearchWidget(tab)
                hierarchical_search.search_root = entity_root
                hierarchical_search.node_activated.connect(
                    lambda entity_type, entity_id, name, path_label, incremental_paths, v=view, pm=proxy_model: self._node_activated(
                        incremental_paths, v, pm
                    )
                )
                model.async_item_retrieval_completed.connect(
                    lambda item, v=view, pm=proxy_model: self._async_item_retrieval_completed(
                        item, v, pm
                    )
                )
                hierarchical_search.set_bg_task_manager(self._task_manager)
                layout.addWidget(hierarchical_search)
                self._dynamic_widgets.append(hierarchical_search)
            # -----------------------------------------------

            # --- Context Menus (logic remains the same) ---
            def action_hovered(action):
                tip = action.toolTip()
                if tip == action.text() or not tip:
                    QToolTip.hideText()
                else:
                    QToolTip.showText(QCursor.pos(), tip)

            view_actions = []
            if type_hierarchy:
                action_ca = QAction("Collapse All Folders", view)
                action_ca.hovered.connect(lambda act=action_ca: action_hovered(act))
                action_ca.triggered.connect(view.collapseAll)
                view_actions.append(action_ca)

                action_reset = QAction("Reset", view)
                action_reset.setToolTip(
                    "<nobr>Reset the tree to its root collapsed state.</nobr>"
                )
                action_reset.hovered.connect(lambda act=action_reset: action_hovered(act))
                action_reset.triggered.connect(model.reload_data)
                view_actions.append(action_reset)
            else:
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
                    "<nobr>Refresh tree data from ShotGrid.</nobr>"
                )
                action_refresh.hovered.connect(lambda act=action_refresh: action_hovered(act))
                action_refresh.triggered.connect(model.async_refresh)
                view_actions.append(action_refresh)

            view.setContextMenuPolicy(Qt.ActionsContextMenu)
            for act in view_actions:
                view.addAction(act)
            self._dynamic_widgets.extend(view_actions)
            # ---------------------------------------------

            # --- Connect Signals & Overlay ---
            selection_model = view.selectionModel()
            selection_model.selectionChanged.connect(self._on_treeview_item_selected)
            overlay = ShotgunModelOverlayWidget(model, view)
            # ---------------------------------

            # --- Store Preset ---
            ep = EntityPreset(
                preset_name, sg_entity_type, model, proxy_model, view, publish_filters
            )
            self._entity_presets[preset_name] = ep
            # Keep references to avoid garbage collection
            self._dynamic_widgets.extend([model, proxy_model, tab, layout, view, selection_model, overlay])
            # --------------------

        # --- Finalize ---
        # Reconnect the main tab change signal now that all tabs are created
        self.ui.entity_preset_tabs.currentChanged.connect(
            self._on_entity_profile_tab_clicked
        )

        # After all presets are loaded, navigate to the default "home" view.
        if self.ui.entity_preset_tabs.count() > 0:
            QtCore.QTimer.singleShot(0, self._on_home_clicked)


    def _get_sync_count_for_entity(self, key):
        return self._sync_manager.get_sync_count_for_entity(key)

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

    #---------------------------------------------------

    def _on_treeview_item_selected(self):
        """
        Slot triggered when someone changes the selection in a treeview.
        Handles both specific entity selections (Assets, Shots, Tasks) and
        intermediate grouping nodes (Asset Types, Statuses, etc.).
        Updates sync count for the selected entity on-demand with caching.
        """
        logger.debug("Treeview item selection changed.")
        self._fstat_dict = {}  # Reset Perforce status

        # 1. Get the selected item from the tree view
        selected_item = self._get_selected_entity()

        # --- Handle case where nothing is selected (e.g., clearing selection) ---
        if not selected_item:
            logger.debug("No item selected in the tree view. Clearing UI.")
            self._clear_ui_on_no_selection()
            return

        # 2. Extract data from the selected tree item
        sg_data_from_tree, field_value_from_tree = model_item_data.get_item_data(selected_item)
        logger.debug(
            f"Extracted data from selected tree item: sg_data={sg_data_from_tree}, field_value={field_value_from_tree}")

        # 3. Determine if the selection is a specific entity or an intermediate node
        is_specific_entity = False
        entity_data_clicked = None

        if isinstance(field_value_from_tree, dict) and field_value_from_tree.get("type") and field_value_from_tree.get(
                "id"):
            entity_data_clicked = field_value_from_tree  # e.g., Task data from 'My Tasks'
            is_specific_entity = True
        elif isinstance(sg_data_from_tree, dict) and sg_data_from_tree.get("type") and sg_data_from_tree.get("id"):
            entity_data_clicked = sg_data_from_tree  # e.g., Asset data from 'Assets'
            is_specific_entity = True

        # 4. Store the resolved entity data
        self._entity_data = entity_data_clicked  # Store the resolved entity data (or None)

        # 5. Perform UI updates common to both selection types
        self._populate_entity_breadcrumbs(selected_item)
        self._add_file_history_record(self._current_entity_preset, selected_item)
        self._setup_file_details_panel([])  # Clear details panel initially

        # 6. Load publishes for the selected item (handles both entities and folders)
        self._load_publishes_for_entity_item(selected_item)

        # 7. Handle specific entity selection
        if is_specific_entity:
            logger.debug(f"Processing as specific entity: {self._entity_data}")

            # Get filesystem path
            self._entity_path, entity_id, entity_type = self._get_entity_info(self._entity_data)
            logger.debug(f"Entity path determined as: {self._entity_path}")

            # Update sync count display for this entity
            if self._entity_path:
                self._update_sync_count_for_selected_item(selected_item, self._entity_path, entity_id, entity_type)

            # Get current SG data and Perforce data
            self.get_current_sg_data()
            self._update_perforce_data()

            # Resolve entity for panel navigation (handles Tasks correctly)
            target_entity_for_panel = self._resolve_entity_for_panel(self._entity_data)

            # Schedule panel update
            logger.debug(f"Scheduling panel update for: {target_entity_for_panel}")
            QtCore.QTimer.singleShot(0, lambda: self._get_shotgun_panel_widget(target_entity_for_panel))

        else:
            # --- An intermediate grouping node was selected ---
            logger.debug(f"Processing as intermediate node: {field_value_from_tree}")
            self._clear_entity_specific_data()

            # Update sync count for intermediate nodes if applicable
            self._update_sync_count_for_intermediate_node(selected_item)

            # Clear the panel since no specific entity is selected
            QtCore.QTimer.singleShot(0, lambda: self._get_shotgun_panel_widget(None))

        # 8. Refresh views that depend on the newly populated data
        self._refresh_dependent_views()

        logger.debug("Finished _on_treeview_item_selected.")

    def _get_sync_count_for_entity_cached(self, entity_path):
        return self._sync_manager.get_sync_count_for_entity_cached(entity_path)

    def _invalidate_sync_cache(self, entity_path=None):
        self._sync_manager.invalidate_sync_cache(entity_path)

    def _clear_ui_on_no_selection(self):
        """Clear all UI elements when no item is selected."""
        self._publish_model.clear()
        self._sg_data = []
        self._fstat_dict = {}
        self._entity_path = None
        self._entity_data = None
        self._setup_file_details_panel([])
        QtCore.QTimer.singleShot(0, lambda: self._get_shotgun_panel_widget(None))

        if self.main_view_mode == self.MAIN_VIEW_COLUMN:
            self.column_view_model.setRowCount(0)
        if self.main_view_mode == self.MAIN_VIEW_SUBMITTED:
            self._reset_submitted_widget()

    def _clear_entity_specific_data(self):
        """Clear data specific to entity selection."""
        self._entity_path = None
        self._sg_data = []
        self._fstat_dict = {}

    def _resolve_entity_for_panel(self, entity_data):
        """
        Resolve the correct entity for panel navigation.
        For Tasks, returns the linked entity (Asset/Shot).
        For other entities, returns the entity itself.
        """
        if not entity_data:
            return None

        if entity_data.get("type") == "Task":
            linked_entity = entity_data.get("entity")
            if linked_entity and isinstance(linked_entity, dict):
                return linked_entity

        return entity_data

    def _update_sync_count_for_selected_item(self, selected_item, entity_path, entity_id, entity_type):
        """
        Update the sync count display for the selected entity item.
        This is called on-demand when a specific entity is selected.
        Uses caching for improved performance.
        """
        try:
            # First, immediately show "Checking..." status
            self._display_sync_count_in_tree(selected_item, -1)  # Special value for checking

            # Get sync count asynchronously to avoid blocking UI
            def update_sync_display():
                # Use cached version for better performance
                sync_count = self._get_sync_count_for_entity_cached(entity_path)
                self._display_sync_count_in_tree(selected_item, sync_count)
                logger.debug(f"Updated sync count for {entity_type} {entity_id}: {sync_count}")

            # Use shorter timer for faster response
            QtCore.QTimer.singleShot(10, update_sync_display)  # Reduced from 100ms to 10ms

        except Exception as e:
            logger.error(f"Error updating sync count for selected item: {e}")

    def _update_sync_count_for_intermediate_node(self, selected_item):
        """
        Update sync count for intermediate nodes (like asset types, statuses).
        Shows aggregate sync count for all children.
        """
        # This is optional - you may want to show aggregate counts for folders
        # For now, we'll just ensure the second column exists but leave it empty
        preset = self._entity_presets.get(self._current_entity_preset)
        if preset:
            self._ensure_sync_column_exists(preset)

    def _display_sync_count_in_tree(self, selected_item, sync_count):
        """
        Display the sync count in the tree view for the selected item.
        Always displays the value, even if it's 0.
        """
        preset = self._entity_presets.get(self._current_entity_preset)
        if not preset:
            return

        # Ensure the sync column exists
        self._ensure_sync_column_exists(preset)

        # Get the source model
        proxy_model = preset.proxy_model
        source_model = proxy_model.sourceModel()

        # Create sync status message - always show a value
        if sync_count == -1:
            msg = "Checking..."
        elif sync_count == 0:
            msg = "Up to date"
        else:
            msg = "{} files".format(sync_count)

        logger.debug(f"[SYNC DISPLAY] Setting sync status for item '{selected_item.text()}': {msg}")

        # Find the sync item for this row
        # We need to get the item in column 1 at the same tree level
        parent = selected_item.parent()
        row = selected_item.row()

        # Create or get the sync status item
        sync_item = None
        if parent:
            # Child item - get from parent
            sync_item = parent.child(row, 1)
            if not sync_item:
                sync_item = QStandardItem()
                parent.setChild(row, 1, sync_item)
                logger.debug(f"Created new sync item as child at row {row}")
        else:
            # Root level item - get from model
            sync_item = source_model.item(row, 1)
            if not sync_item:
                sync_item = QStandardItem()
                source_model.setItem(row, 1, sync_item)
                logger.debug(f"Created new sync item at root level row {row}")

        # Update the sync item
        sync_item.setText(msg)

        # Set icon if available (no icon for "checking" state)
        if sync_count >= 0:
            sync_icon = self.sync_icons.get_sync_pixmap(sync_count)
            if sync_icon:
                sync_item.setIcon(sync_icon)
            else:
                sync_item.setIcon(QIcon())
        else:
            sync_item.setIcon(QIcon())  # Clear icon for checking state

        # Ensure the item is visible in the view
        view = preset.view
        if view and sync_item.index().isValid():
            # Map to proxy index if needed
            proxy_index = proxy_model.mapFromSource(sync_item.index())
            if proxy_index.isValid():
                view.update(proxy_index)

        # Force model update
        if sync_item.index().isValid():
            source_model.dataChanged.emit(sync_item.index(), sync_item.index())

    def _ensure_sync_column_exists(self, preset):
        """
        Ensure the tree view has a second column for sync status.
        """
        proxy_model = preset.proxy_model
        source_model = proxy_model.sourceModel()
        view = preset.view

        # Add second column if it doesn't exist
        if source_model.columnCount() < 2:
            source_model.setColumnCount(2)
            source_model.setHorizontalHeaderLabels(["Name", "To Sync"])

            # Configure view to show both columns
            view.setHeaderHidden(False)
            view.header().setStretchLastSection(False)
            view.header().setSectionResizeMode(0, QHeaderView.Stretch)
            view.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            view.setSortingEnabled(True)

    def _refresh_dependent_views(self):
        """
        Refresh views that depend on the selected entity data.
        """
        if self.main_view_mode == self.MAIN_VIEW_COLUMN:
            logger.debug("Scheduling Column View update.")
            QtCore.QTimer.singleShot(0, self._set_column_view_mode)
        elif self.main_view_mode == self.MAIN_VIEW_SUBMITTED:
            logger.debug("Scheduling Submitted View update.")
            QtCore.QTimer.singleShot(0, self._populate_submitted_widget)
        # Add other view modes as needed

    def _after_syncing_operations(self):
        """
        Called after sync operations complete.
        Invalidates cache for the current entity.
        """
        # Hide sync progress UI and restore determinate mode
        self.ui.cancel_sync.setVisible(False)
        self.ui.sync_status_label.setVisible(False)
        self.ui.progress.setRange(0, 100)
        self.ui.progress.setValue(0)
        self.ui.progress.setVisible(False)

        # Re-enable sync buttons
        self.ui.sync_files.setEnabled(True)
        self.ui.sync_parents.setEnabled(True)
        self.ui.get_latest_button.setEnabled(True)

        # Invalidate cache for the current entity path
        if self._entity_path:
            self._invalidate_sync_cache(self._entity_path)

        # Reload data
        self._add_log("\n <span style='color:#2C93E2'>Reloading data ...</span> \n", 2)
        self._status_model.hard_refresh()
        self._publish_file_history_model.hard_refresh()
        self._publish_model.hard_refresh()
        self._setup_file_details_panel([])

        if self.main_view_mode == self.MAIN_VIEW_COLUMN:
            self._update_perforce_data()
            self._populate_column_view_widget()

    # ---------------------------------------------------

    def get_current_sg_data(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.get_current_sg_data()
        self._sg_data = self._publish_integration._sg_data

    def get_current_publish_data(self, entity_id, entity_type):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.get_current_publish_data(entity_id, entity_type)
        self._sg_data = self._publish_integration._sg_data

    def _update_perforce_data(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.set_entity_path(self._entity_path)
        self._publish_integration._update_perforce_data()
        self._fstat_dict = self._publish_integration._fstat_dict
        self._item_path_dict = self._publish_integration._item_path_dict

    def print_publish_data(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.print_publish_data()

    def _update_fstat_data(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._update_fstat_data()
        self._fstat_dict = self._publish_integration._fstat_dict

    def _fix_fstat_dict(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._fix_fstat_dict()

    def _get_submitted_changelists(self, folder_path):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_submitted_changelists(folder_path)

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
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.on_publish_model_action(action)

    def perform_changelist_selection(self, selected_actions):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.perform_changelist_selection(selected_actions)

    def refresh_publish_data(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration.refresh_publish_data()

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
        Handles UI updates related to tree view selection *before*
        the main data loading in _on_treeview_item_selected.
        Returns the selected QStandardItem.
        """
        selected_item = self._get_selected_entity()

        # Update breadcrumbs (Moved to _on_treeview_item_selected)
        # self._populate_entity_breadcrumbs(selected_item)

        # Fetch more items in the tree if needed
        if selected_item:
            model = self._entity_presets[self._current_entity_preset].model
            if model.canFetchMore(selected_item.index()):
                model.fetchMore(selected_item.index())

        # Add to history (Moved to _on_treeview_item_selected)
        # self._add_file_history_record(self._current_entity_preset, selected_item)

        # Clear details panel (Moved to _on_treeview_item_selected)
        # self._setup_file_details_panel([])

        # Trigger publish model load (Moved to _on_treeview_item_selected)
        # self._load_publishes_for_entity_item(selected_item)

        # Return ONLY the selected item
        return selected_item

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
    def _convert_local_to_depot(self, local_path):
        return local_to_depot(local_path)

    def _get_perforce_data(self):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        self._publish_integration._get_perforce_data()
        self._fstat_dict = self._publish_integration._fstat_dict
        self._item_path_dict = self._publish_integration._item_path_dict

    def _get_file_log(self, file_path, head_rev):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_file_log(file_path, head_rev)

    def _get_publish_type(self, publish_path):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_publish_type(publish_path)

    def _get_p4_status(self, p4_status):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_p4_status(p4_status)

    def _get_small_perforce_data(self, sg_data):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._get_small_perforce_data(sg_data)

    def _get_latest_revision(self, files_to_sync):
        self._sync_manager.get_latest_revision(files_to_sync)



    def _find_task_context(self, path):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._find_task_context(path)

    def _find_context(self, tk, context, path):
        """Compatibility wrapper -- delegates to PublishIntegration."""
        return self._publish_integration._find_context(tk, context, path)

class EntityPreset(object):
    def __init__(self, name, entity_type, model, proxy_model, view, publish_filters):
        self.model = model
        self.proxy_model = proxy_model
        self.name = name
        self.view = view
        self.entity_type = entity_type
        self.publish_filters = publish_filters

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

class LogUpdater(QtCore.QObject):
    updateLog = QtCore.Signal(str, int)

    def __init__(self, parent=None):
        super(LogUpdater, self).__init__(parent)
        self.updateLog.connect(self._add_log_slot)

    def _add_log_slot(self, msg, flag):
        if flag <= 2:
            msg = "\n{}\n".format(msg)
        else:
            msg = "{}".format(msg)
        self.parent().ui.log_window.append(msg)
        # if flag < 4:
        #     logger.debug(msg)
        self.parent().ui.log_window.verticalScrollBar().setValue(
            self.parent().ui.log_window.verticalScrollBar().maximum()
        )

class ProgressUpdater(QtCore.QObject):
    """
    A Qt object to handle thread-safe progress bar updates via signals.
    """
    update_progress = QtCore.Signal(float)

    def __init__(self, progress_widget, dialog):
        """
        Initialize the ProgressUpdater with a progress widget and dialog.

        Args:
            progress_widget (QProgressBar): The progress bar widget to update.
            dialog (QDialog): The parent dialog containing the UI.
        """
        super(ProgressUpdater, self).__init__()
        self._progress_widget = progress_widget
        self._dialog = dialog
        self.update_progress.connect(self._update_progress_slot)

    def _update_progress_slot(self, value):
        """
        Slot to update the progress bar with the given value.

        Args:
            value (float): Progress value between 0 and 100.
        """
        if not self._dialog or not self._progress_widget or not self._dialog.isVisible():
            logger.debug("Skipping progress update: dialog or progress widget is invalid or not visible")
            return
        if value > 0:
            int_val = max(1, min(int(value), 100))
            logger.debug("ProgressUpdater setting bar to %d (raw=%.2f)", int_val, value)
            self._progress_widget.setValue(int_val)
            self._progress_widget.setVisible(True)
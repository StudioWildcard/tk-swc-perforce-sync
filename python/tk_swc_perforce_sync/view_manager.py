# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
ViewManager - Owns view mode switching (5 modes), column view (grouping, table,
context menus), details pane, file details panel, and publish view interaction.
"""

import os
import datetime
import logging

import sgtk

from sgtk.platform.qt import QtCore
for name, cls in QtCore.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

from sgtk.platform.qt import QtGui
for name, cls in QtGui.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

from . import constants
from .date_time import create_modified_date

logger = sgtk.platform.get_logger(__name__)

# import frameworks
shotgun_model = sgtk.platform.import_framework(
    "tk-swc-framework-shotgunutils", "shotgun_model"
)
shotgun_globals = sgtk.platform.import_framework(
    "tk-swc-framework-shotgunutils", "shotgun_globals"
)
help_screen = sgtk.platform.import_framework("tk-framework-qtwidgets", "help_screen")


class ViewManager(QtCore.QObject):
    """
    Manages view mode switching, column view, details pane, and publish view
    interaction for the AppDialog.

    Signals:
        column_view_action_requested(str, list): Emitted when a column view
            context menu action is triggered. Args: (action_name, [(sg_item, action)...])
        log_message(str, int): Routed to AppDialog's _add_log.
    """

    # View mode constants
    (MAIN_VIEW_LIST, MAIN_VIEW_THUMB, MAIN_VIEW_COLUMN, MAIN_VIEW_SUBMITTED, MAIN_VIEW_PENDING) = range(5)

    # Column view grouping constants
    (COLUMN_VIEW_UNGROUP, COLUMN_VIEW_GROUP_BY_FOLDER, COLUMN_VIEW_GROUP_BY_ACTION,
     COLUMN_VIEW_GROUP_BY_REVISION, COLUMN_VIEW_GROUP_BY_EXTENSION, COLUMN_VIEW_GROUP_BY_TYPE,
     COLUMN_VIEW_GROUP_BY_USER, COLUMN_VIEW_GROUP_BY_TASK, COLUMN_VIEW_GROUP_BY_STATUS,
     COLUMN_VIEW_GROUP_BY_STEP, COLUMN_VIEW_GROUP_BY_DATE_MODIFIED) = range(11)

    # Signals
    column_view_action_requested = QtCore.Signal(str, list)
    log_message = QtCore.Signal(str, int)

    def __init__(self, app, ui, settings_manager, action_manager,
                 publish_model, publish_proxy_model, status_model,
                 publish_file_history_model, publish_type_model,
                 actions_icons, dynamic_widgets, parent=None):
        """
        :param app: The sgtk app bundle.
        :param ui: The Ui_Dialog instance.
        :param settings_manager: UserSettings instance.
        :param action_manager: LoaderActionManager instance.
        :param publish_model: SgLatestPublishModel instance.
        :param publish_proxy_model: SgLatestPublishProxyModel instance.
        :param status_model: SgStatusModel instance.
        :param publish_file_history_model: SgPublishHistoryModel instance.
        :param publish_type_model: SgPublishTypeModel instance.
        :param actions_icons: Icons instance for action icons.
        :param dynamic_widgets: List reference for GC protection of dynamic widgets.
        :param parent: Parent QObject.
        """
        super(ViewManager, self).__init__(parent)
        self._app = app
        self.ui = ui
        self._settings_manager = settings_manager
        self._action_manager = action_manager
        self._publish_model = publish_model
        self._publish_proxy_model = publish_proxy_model
        self._status_model = status_model
        self._publish_file_history_model = publish_file_history_model
        self._publish_type_model = publish_type_model
        self.actions_icons = actions_icons
        self._dynamic_widgets = dynamic_widgets

        # Extension type map for column view
        self.settings = constants.EXTENSION_TYPE_MAP

        # View state
        self.main_view_mode = self.MAIN_VIEW_THUMB
        self._current_column_view_grouping = self.COLUMN_VIEW_UNGROUP
        self._column_view_search_filter = None
        self._set_groups = False
        self._details_pane_visible = False

        # Column view data
        self._column_view_dict = {}
        self._standard_item_dict = {}
        self._perforce_sg_data = []
        self._publish_icons = {}

        # Grouping dictionaries
        self._folder_dict = {}
        self._action_dict = {}
        self._revision_dict = {}
        self._file_extension_dict = {}
        self._type_dict = {}
        self._task_name_dict = {}
        self._task_status_dict = {}
        self._user_dict = {}
        self._step_dict = {}
        self._date_modified_dict = {}

        # Column view models
        self.column_view_model = None
        self.perforce_proxy_model = None

        # Detail panel state
        self._file_details_action_menu = QMenu()
        self.ui.file_detail_actions_btn.setMenu(self._file_details_action_menu)
        self._current_version_detail_playback_url = None

        # Entity path (set externally when entity selection changes)
        self._entity_path = None

        # Icons for view mode buttons
        repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.active_column_view_icon = QIcon(QPixmap(
            os.path.join(repo_root, "icons/mode_switch_column_active.png")))
        self.inactive_column_view_icon = QIcon(QPixmap(
            os.path.join(repo_root, "icons/mode_switch_column_off.png")))
        self.submitted_icon = QIcon(QPixmap(
            os.path.join(repo_root, "icons/mode_switch_submitted_active.png")))
        self.submitted_icon_inactive = QIcon(QPixmap(
            os.path.join(repo_root, "submitted_off.png")))
        self.pending_icon = QIcon(QPixmap(
            os.path.join(repo_root, "icons/mode_switch_pending_active.png")))
        self.pending_icon_inactive = QIcon(QPixmap(
            os.path.join(repo_root, "icons/pending_off.png")))

        # Column headers
        self._headers = ["", "Folder", "Action", "Name", "Revision#", "Size(MB)",
                         "Extension", "Type", "User", "Task", "Status", "Step",
                         "Date/Time", "Date Modified", "ID", "Description"]

        # Setup column view
        self._setup_column_view()

    # -----------------------------------------------------------------------
    # Entity path setter (called by AppDialog when entity selection changes)
    # -----------------------------------------------------------------------

    def set_entity_path(self, entity_path):
        self._entity_path = entity_path

    # -----------------------------------------------------------------------
    # View mode switching
    # -----------------------------------------------------------------------

    def on_thumbnail_mode_clicked(self):
        self.set_main_view_mode(self.MAIN_VIEW_THUMB)

    def on_list_mode_clicked(self):
        self.set_main_view_mode(self.MAIN_VIEW_LIST)

    def on_column_mode_clicked(self):
        self.set_main_view_mode(self.MAIN_VIEW_COLUMN)

    def on_submitted_mode_clicked(self):
        self.set_main_view_mode(self.MAIN_VIEW_SUBMITTED)

    def on_pending_mode_clicked(self):
        self.set_main_view_mode(self.MAIN_VIEW_PENDING)

    def set_main_view_mode(self, mode):
        """
        Sets up the view mode for the main view.

        :param mode: One of MAIN_VIEW_LIST, MAIN_VIEW_THUMB, MAIN_VIEW_COLUMN,
                     MAIN_VIEW_SUBMITTED, MAIN_VIEW_PENDING
        """
        from sgtk import TankError

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
            self.main_view_mode = self.MAIN_VIEW_LIST
            self._set_button_states_for_list_thumb()
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
            self._set_button_states_for_list_thumb()
            self.ui.get_latest_button.setEnabled(True)
            self.ui.submit_button.setEnabled(False)

        elif mode == self.MAIN_VIEW_COLUMN:
            self._turn_all_modes_off()
            self.ui.column_view.setVisible(True)
            self.ui.column_mode.setIcon(self.active_column_view_icon)
            self.ui.column_mode.setChecked(True)
            self.main_view_mode = self.MAIN_VIEW_COLUMN
            self.ui.publish_view.setItemDelegate(self._publish_list_delegate)
            self._populate_column_view_widget()
            self._set_button_states_for_list_thumb()
            self.ui.get_latest_button.setEnabled(True)
            self.ui.submit_button.setEnabled(False)

        elif mode == self.MAIN_VIEW_SUBMITTED:
            self._turn_all_modes_off()
            self.ui.submitted_scroll.setVisible(True)
            self.ui.submitted_mode.setIcon(self.submitted_icon)
            self.ui.submitted_mode.setChecked(True)
            self.main_view_mode = self.MAIN_VIEW_SUBMITTED
            # Submitted widget population is handled by AppDialog
            self.ui.sync_files.setEnabled(False)
            self.ui.sync_parents.setEnabled(False)
            self.ui.fix_selected.setEnabled(True)
            self.ui.fix_all.setEnabled(True)
            self.ui.submit_files.setEnabled(False)
            self.ui.get_latest_button.setEnabled(False)
            self.ui.submit_button.setEnabled(False)

        elif mode == self.MAIN_VIEW_PENDING:
            self._turn_all_modes_off()
            self.ui.pending_scroll.setVisible(True)
            self.ui.pending_mode.setIcon(self.pending_icon)
            self.ui.pending_mode.setChecked(True)
            self.main_view_mode = self.MAIN_VIEW_PENDING
            self.ui.sync_files.setEnabled(False)
            self.ui.sync_parents.setEnabled(False)
            self.ui.fix_selected.setEnabled(False)
            self.ui.fix_all.setEnabled(False)
            self.ui.submit_files.setEnabled(True)
            self.ui.get_latest_button.setEnabled(False)
            self.ui.submit_button.setEnabled(True)
        else:
            raise TankError("Undefined view mode!")

        self.ui.publish_view.selectionModel().clear()
        self._settings_manager.store("main_view_mode", mode)

    def _set_button_states_for_list_thumb(self):
        """Sets common button states for list/thumb/column modes."""
        self.ui.sync_files.setEnabled(True)
        self.ui.sync_parents.setEnabled(True)
        self.ui.fix_selected.setEnabled(False)
        self.ui.fix_all.setEnabled(False)
        self.ui.submit_files.setEnabled(False)

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

        repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        inactive_column_view_icon = QIcon(QPixmap(
            os.path.join(repo_root, "icons/mode_switch_column_off.png")))
        submitted_icon_inactive = QIcon(QPixmap(
            os.path.join(repo_root, "icons/submitted_off.png")))
        pending_icon_inactive = QIcon(QPixmap(
            os.path.join(repo_root, "icons/pending_off.png")))

        self.ui.column_mode.setIcon(inactive_column_view_icon)
        self.ui.submitted_mode.setIcon(submitted_icon_inactive)
        self.ui.pending_mode.setIcon(pending_icon_inactive)
        self._show_thumb_scale(False)

    def _show_thumb_scale(self, is_visible):
        self.ui.thumb_scale.setVisible(is_visible)
        self.ui.scale_label.setVisible(is_visible)

    # -----------------------------------------------------------------------
    # Delegate setters (called by AppDialog after delegates are created)
    # -----------------------------------------------------------------------

    def set_delegates(self, publish_list_delegate, publish_thumb_delegate):
        self._publish_list_delegate = publish_list_delegate
        self._publish_thumb_delegate = publish_thumb_delegate

    def set_pixmaps(self, no_selection_pixmap, multiple_publishes_pixmap, no_pubs_found_icon):
        self._no_selection_pixmap = no_selection_pixmap
        self._multiple_publishes_pixmap = multiple_publishes_pixmap
        self._no_pubs_found_icon = no_pubs_found_icon

    def set_publish_main_overlay(self, overlay):
        self._publish_main_overlay = overlay

    # -----------------------------------------------------------------------
    # Column view setup
    # -----------------------------------------------------------------------

    def _setup_column_view(self):
        self.column_view_model = QStandardItemModel(0, len(self._headers))
        self.column_view_model.setHorizontalHeaderLabels(self._headers)

        self.perforce_proxy_model = QtGui.QSortFilterProxyModel()
        self.perforce_proxy_model.setSourceModel(self.column_view_model)

        self.ui.column_view.setModel(self.perforce_proxy_model)

        header = self.ui.column_view.header()
        for col in range(len(self._headers)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        self.ui.column_view.clicked.connect(self.on_column_view_row_clicked)

        self._create_column_view_context_menu()
        self._create_column_view_header_context_menu()

    # -----------------------------------------------------------------------
    # Column view population
    # -----------------------------------------------------------------------

    def populate_column_view_widget(self):
        """Public entry point for populating the column view.
        Requires that _sg_data and _item_path_dict are set on AppDialog."""
        self._populate_column_view_widget()

    def _populate_column_view_widget(self):
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
            msg = "\n <span style='color:#2C93E2'>Populating the Column View with {} files. Please wait...</span> \n".format(length)
            self.log_message.emit(msg, 2)
            logger.debug("Getting Perforce file size...")
            self._perforce_sg_data = self._get_perforce_size(self._perforce_sg_data)
            logger.debug("Populating Column View table...")
            logger.debug("Updating Column View is complete")

            for sg_item in self._perforce_sg_data:
                id = sg_item.get("id", 0)
                new_sg_item, sg_list = self._get_column_data(sg_item)
                if id not in self._column_view_dict and new_sg_item:
                    self._column_view_dict[id] = new_sg_item
                if sg_list:
                    self._standard_item_dict[id] = sg_list
            self._get_grouped_column_view_data()
            self._get_publish_icons()
            self._set_column_group()

    def set_sg_data(self, sg_data):
        """Set the SG data reference for column view population."""
        self._sg_data = sg_data

    def set_item_path_dict(self, item_path_dict):
        """Set the item path dict for file size lookup."""
        self._item_path_dict = item_path_dict

    def set_p4_and_helpers(self, p4, create_key_fn, convert_local_to_depot_fn):
        """Set the P4 connection and helper functions needed for column view."""
        self._p4 = p4
        self._create_key = create_key_fn
        self._convert_local_to_depot = convert_local_to_depot_fn

    def set_get_entity_path_fn(self, fn):
        """Set the _get_entity_path function from AppDialog."""
        self._get_entity_path_fn = fn

    # -----------------------------------------------------------------------
    # Column data extraction
    # -----------------------------------------------------------------------

    def _get_column_data(self, sg_item):
        new_sg_item = sg_item
        sg_list = []
        if not sg_item:
            return new_sg_item, sg_list

        name = sg_item.get("name", "N/A")
        new_sg_item["name"] = name
        action = sg_item.get("action") or sg_item.get("headAction") or "N/A"
        new_sg_item["action"] = action
        revision = sg_item.get("revision", "N/A")
        if revision != "N/A":
            new_sg_item["revision"] = revision

        local_path = "N/A"
        folder = "N/A"
        if "path" in sg_item:
            path = sg_item.get("path", None)
            if path:
                local_path = path.get("local_path", "N/A")
                if local_path and local_path != "N/A":
                    local_directory = os.path.dirname(local_path)
                    entity_path = self._entity_path
                    if local_directory and not entity_path:
                        entity = sg_item.get("entity", None)
                        if entity:
                            entity_path = self._get_entity_path_fn(entity)

                    if entity_path and local_directory:
                        logger.debug("entity_path: {}".format(entity_path))
                        logger.debug("local_directory: {}".format(local_directory))
                        folder = self._path_difference(entity_path, local_directory)

                    if local_directory and not entity_path:
                        folder = os.path.basename(local_directory)
                        logger.debug("No entity path found, we will use parent folder: {}".format(folder))
                    if folder and folder != "N/A":
                        new_sg_item["folder"] = folder

        file_extension = "N/A"
        if local_path and local_path != "N/A":
            file_extension = local_path.split(".")[-1] or "N/A"
            new_sg_item["file_extension"] = file_extension

        type_name = "N/A"
        if file_extension and file_extension != "N/A":
            type_name = self.settings.get(file_extension, "N/A")
            new_sg_item["file_type"] = type_name

        size = sg_item.get("fileSize", 0)
        new_sg_item["size"] = size

        description = sg_item.get("description", "N/A")
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
                if not step:
                    step = self._get_pipeline_step(publish_id)
                new_sg_item["step"] = step

        task_status = sg_item.get("task.Task.sg_status_list", "N/A")
        new_sg_item["task_status"] = task_status

        user = "N/A"
        if "created_by" in sg_item:
            user = sg_item.get("created_by", None)
            if user:
                user = user.get("name", "N/A")
                new_sg_item["user"] = user

        dt = sg_item.get("created_at") or sg_item.get("headModTime") or sg_item.get("headTime") or None
        dt = float(dt) if dt else 0
        date = self._get_publish_time_for_column_view(dt)
        new_sg_item["date"] = date
        date_modified = self._get_modified_date(dt)
        new_sg_item["date_modified"] = date_modified

        sg_list = ["", folder, action, name, revision, size, file_extension,
                   type_name, user, task_name, task_status, step, date,
                   date_modified, publish_id, description]

        return new_sg_item, sg_list

    def _get_pipeline_step(self, published_file_id):
        pipeline_step = "N/A"
        published_file = self._app.shotgun.find_one(
            "PublishedFile",
            [["id", "is", published_file_id]],
            ["id", "code", "pipeline_step", "task.Task.step.Step.code", "step"]
        )
        if published_file:
            pipeline_step = published_file.get("task.Task.step.Step.code", "N/A")
        return pipeline_step

    def _get_modified_date(self, dt):
        publish_time = "N/A"
        if dt and dt > 0:
            try:
                dt_datetime = datetime.datetime.fromtimestamp(dt)
                publish_time = create_modified_date(dt_datetime)
            except ValueError as e:
                logger.error(f"Error converting timestamp {dt} to datetime: {e}")
                publish_time = "Invalid Date"
            except Exception as e:
                logger.error(f"Error in create_modified_date for timestamp {dt}: {e}")
                publish_time = "Error"
        return publish_time

    def _get_publish_time_for_column_view(self, dt):
        publish_time = "N/A"
        if dt > 0:
            publish_time = datetime.datetime.fromtimestamp(dt).strftime("%Y-%m-%d %H:%M")
        return publish_time

    @staticmethod
    def _path_difference(path1, path2):
        path1 = os.path.normpath(path1)
        path2 = os.path.normpath(path2)
        components1 = path1.split(os.sep)
        components2 = path2.split(os.sep)
        common_prefix = []
        for component1, component2 in zip(components1, components2):
            if component1 == component2:
                common_prefix.append(component1)
            else:
                break
        diff2 = components2[len(common_prefix):]
        return os.sep.join(diff2)

    # -----------------------------------------------------------------------
    # Perforce data helpers for column view
    # -----------------------------------------------------------------------

    def _get_perforce_sg_data(self):
        from .model_latestpublish import SgLatestPublishModel
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
                    sg_item = shotgun_model.get_sg_data(model_index)
                    if sg_item:
                        perforce_sg_data.append(sg_item)
        return perforce_sg_data

    def _get_perforce_size(self, sg_data):
        try:
            self._size_dict = {}
            for key in self._item_path_dict:
                if key:
                    key = self._convert_local_to_depot(key).rstrip('/')
                    fstat_list = self._p4.run("fstat", "-T", "fileSize, clientFile", "-Ol", key + '/...')
                    for fstat in fstat_list:
                        if fstat:
                            size = fstat.get("fileSize", "N/A")
                            if size != "N/A":
                                size = "{:.2f}".format(int(size) / 1024 / 1024)
                                size = float(size)
                            client_file = fstat.get('clientFile', None)
                            if client_file:
                                newkey = self._create_key(client_file)
                                if newkey:
                                    if newkey not in self._size_dict:
                                        self._size_dict[newkey] = {}
                                    self._size_dict[newkey]['fileSize'] = size

                    for i, sg_item in enumerate(sg_data):
                        if "path" in sg_item:
                            if "local_path" in sg_item["path"]:
                                local_path = sg_item["path"].get("local_path", None)
                                modified_local_path = self._create_key(local_path)
                                if modified_local_path and modified_local_path in self._size_dict:
                                    if 'fileSize' in self._size_dict[modified_local_path]:
                                        sg_item["fileSize"] = self._size_dict[modified_local_path].get('fileSize', None)
        except Exception as e:
            logger.debug("Error getting Perforce file size: {}".format(e))
        return sg_data

    # -----------------------------------------------------------------------
    # Column view grouping
    # -----------------------------------------------------------------------

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
                if value is not None and key != "folder":
                    column_dict.setdefault(value, []).append(self._standard_item_dict.get(id))
                else:
                    column_dict.setdefault(value or "N/A", []).append(self._standard_item_dict.get(id))
        return column_dict

    def _apply_grouping_and_update_view(self, grouping_mode, group_dict, group_column_name):
        self._set_groups = True
        self._current_column_view_grouping = grouping_mode
        self._create_groups(group_dict)
        try:
            column_to_hide_index = self._headers.index(group_column_name)
            self.ui.column_view.setColumnHidden(column_to_hide_index, True)
            logger.debug(f"Hiding column '{group_column_name}' at index {column_to_hide_index}.")
        except ValueError:
            logger.warning(f"Could not find column '{group_column_name}' in headers to hide.")
        grouping_header_item = QStandardItem(group_column_name)
        self.column_view_model.setHorizontalHeaderItem(0, grouping_header_item)
        logger.debug(f"Setting header of column 0 to '{group_column_name}'.")

    def _no_groups(self):
        self._setup_column_view()
        self._current_column_view_grouping = self.COLUMN_VIEW_UNGROUP
        self._populate_column_view_no_groups()

    def _group_by_folder(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_FOLDER, self._folder_dict, "Folder")

    def _group_by_action(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_ACTION, self._action_dict, "Action")

    def _group_by_revision(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_REVISION, self._revision_dict, "Revision#")

    def _group_by_file_extension(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_EXTENSION, self._file_extension_dict, "Extension")

    def _group_by_type(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_TYPE, self._type_dict, "Type")

    def _group_by_user(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_USER, self._user_dict, "User")

    def _group_by_task_name(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_TASK, self._task_name_dict, "Task")

    def _group_by_task_status(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_STATUS, self._task_status_dict, "Status")

    def _group_by_step(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_STEP, self._step_dict, "Step")

    def _group_by_date_modified(self):
        self._apply_grouping_and_update_view(
            self.COLUMN_VIEW_GROUP_BY_DATE_MODIFIED, self._date_modified_dict, "Date Modified")

    def _create_groups(self, group_dict):
        self.setup_file_details_panel([])
        self._setup_column_view()

        for category, sg_data in group_dict.items():
            category_item = QStandardItem(category)
            self.column_view_model.appendRow(category_item)
            for sg_list in sg_data:
                tooltip = ""
                id = 0
                if sg_list and len(sg_list) >= 15:
                    id = sg_list[14]
                    base_name = sg_list[3]
                    if self._column_view_search_filter and len(self._column_view_search_filter) > 1:
                        prefix = self._column_view_search_filter
                        if not base_name.startswith(prefix):
                            continue
                    action = sg_list[2]
                    if action and action in ["delete"]:
                        msg = "\n <span style='color:#2C93E2'>skipping deleted file: {}</span> \n".format(base_name)
                        self.log_message.emit(msg, 2)
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
                        action_icon = self.actions_icons.get_icon_pixmap(action)
                        if action_icon:
                            item.setIcon(action_icon)
                    item.setData(str(id), QtCore.Qt.UserRole + 1)
                    item_list.append(item)
                category_item.appendRow(item_list)

        self.ui.column_view.expandAll()

    def _populate_column_view_no_groups(self):
        row = 0
        self._set_groups = False
        for id, sg_item in self._column_view_dict.items():
            if not sg_item:
                continue
            base_name = sg_item.get("name", None)
            if base_name and self._column_view_search_filter and len(self._column_view_search_filter) > 1:
                prefix = self._column_view_search_filter
                if not base_name.startswith(prefix):
                    continue
            action = sg_item.get("action") or sg_item.get("headAction") or None
            if action and action in ["delete"]:
                msg = "\n <span style='color:#2C93E2'>skipping deleted file: {}</span> \n".format(base_name)
                self.log_message.emit(msg, 2)
                continue
            if id in self._standard_item_dict:
                item_data = self._standard_item_dict[id]
                self._insert_perforce_row(row, item_data, sg_item)
                row += 1

    def _insert_perforce_row(self, row, data, sg_item):
        tooltip = self._get_tooltip(data, sg_item)
        for col, value in enumerate(data):
            item = QStandardItem(str(value))
            item.setToolTip(tooltip)
            if col == 5:
                item.setData(value, Qt.DisplayRole)
            if col == 2:
                action = data[2]
                action_icon = self.actions_icons.get_icon_pixmap(action)
                if action_icon:
                    item.setIcon(action_icon)
            self.column_view_model.setItem(row, col, item)

    def _expand_all(self):
        self.ui.column_view.expandAll()

    def _collapse_all(self):
        self.ui.column_view.collapseAll()

    # -----------------------------------------------------------------------
    # Column view context menus
    # -----------------------------------------------------------------------

    def _create_column_view_context_menu(self):
        self._column_add_action = QAction("Add", self.ui.column_view)
        self._column_add_action.triggered.connect(lambda: self._on_column_model_action("add"))
        self._column_edit_action = QAction("Edit", self.ui.column_view)
        self._column_edit_action.triggered.connect(lambda: self._on_column_model_action("edit"))
        self._column_delete_action = QAction("Delete", self.ui.column_view)
        self._column_delete_action.triggered.connect(lambda: self._on_column_model_action("delete"))
        self._column_revert_action = QAction("Revert", self.ui.column_view)
        self._column_revert_action.triggered.connect(lambda: self._on_column_model_action("revert"))
        self._column_sync_action = QAction("Sync", self.ui.column_view)
        self._column_sync_action.triggered.connect(lambda: self._on_column_model_action("sync"))

        self.ui.column_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.column_view.customContextMenuRequested.connect(self._show_column_actions)

    def _show_column_actions(self, pos):
        menu = QMenu(self.ui.column_view)
        actions = self._action_manager.get_actions_for_publishes(
            self.selected_publishes, self._action_manager.UI_AREA_MAIN
        )
        menu.addActions(actions)
        menu.addSeparator()
        menu.addAction(self._column_add_action)
        menu.addAction(self._column_edit_action)
        menu.addAction(self._column_delete_action)
        menu.addSeparator()
        menu.addAction(self._column_revert_action)
        menu.addSeparator()
        menu.addAction(self._column_sync_action)
        menu.addSeparator()

        global_pos = self.ui.column_view.mapToGlobal(pos)
        event_loop = QEventLoop()
        menu.aboutToHide.connect(event_loop.quit)
        menu.exec_(global_pos)
        event_loop.exec_()

    def _create_column_view_header_context_menu(self):
        header = self.ui.column_view.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_column_header_context_menu)

    def _show_column_header_context_menu(self, pos):
        header = self.ui.column_view.header()
        col_idx = header.logicalIndexAt(pos)
        col_name = self.column_view_model.horizontalHeaderItem(col_idx).text()

        menu = QMenu(self.ui.column_view)

        group_by_folder_action = QAction("Group by folder", self.ui.column_view)
        group_by_folder_action.triggered.connect(self._group_by_folder)
        group_by_action_action = QAction("Group by action", self.ui.column_view)
        group_by_action_action.triggered.connect(self._group_by_action)
        group_by_revision_action = QAction("Group by Revision", self.ui.column_view)
        group_by_revision_action.triggered.connect(self._group_by_revision)
        group_by_file_extension_action = QAction("Group by File Extension", self.ui.column_view)
        group_by_file_extension_action.triggered.connect(self._group_by_file_extension)
        group_by_type_action = QAction("Group by Type", self.ui.column_view)
        group_by_type_action.triggered.connect(self._group_by_type)
        group_by_user_action = QAction("Group by user", self.ui.column_view)
        group_by_user_action.triggered.connect(self._group_by_user)
        group_by_task_name_action = QAction("Group by Task Name", self.ui.column_view)
        group_by_task_name_action.triggered.connect(self._group_by_task_name)
        group_by_task_status_action = QAction("Group by Task Status", self.ui.column_view)
        group_by_task_status_action.triggered.connect(self._group_by_task_status)
        group_by_step_action = QAction("Group by Task Step", self.ui.column_view)
        group_by_step_action.triggered.connect(self._group_by_step)
        group_by_date_modified_action = QAction("Group by Date Modified", self.ui.column_view)
        group_by_date_modified_action.triggered.connect(self._group_by_date_modified)
        no_groups_action = QAction("Ungroup", self.ui.column_view)
        no_groups_action.triggered.connect(self._no_groups)
        expand_all_action = QAction("Expand All", self.ui.column_view)
        expand_all_action.triggered.connect(self._expand_all)
        collapse_all_action = QAction("Collapse All", self.ui.column_view)
        collapse_all_action.triggered.connect(self._collapse_all)

        actions_map = {
            "Folder": [group_by_folder_action],
            "Action": [group_by_action_action],
            "Revision#": [group_by_revision_action],
            "Extension": [group_by_file_extension_action],
            "Type": [group_by_type_action],
            "User": [group_by_user_action],
            "Task": [group_by_task_name_action],
            "Status": [group_by_task_status_action],
            "Step": [group_by_step_action],
            "Date Modified": [group_by_date_modified_action],
        }

        for action in actions_map.get(col_name, []):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(no_groups_action)
        menu.addSeparator()
        menu.addAction(expand_all_action)
        menu.addAction(collapse_all_action)

        global_pos = header.mapToGlobal(pos)
        event_loop = QEventLoop()
        menu.aboutToHide.connect(event_loop.quit)
        menu.exec_(global_pos)
        event_loop.exec_()

    # -----------------------------------------------------------------------
    # Column view row click handlers
    # -----------------------------------------------------------------------

    def on_column_view_row_clicked(self, index):
        if self._set_groups:
            self._on_column_view_row_clicked_group(index)
        else:
            self._on_column_view_row_clicked_no_groups(index)

    def _on_column_view_row_clicked_no_groups(self, index):
        source_index = self.perforce_proxy_model.mapToSource(index)
        row_number = source_index.row()
        item = self.column_view_model.item(row_number, 14)
        if item:
            data = item.text()
            if data and data != "N/A":
                id = int(data)
                self._setup_column_details_panel(id)

    def _on_column_view_row_clicked_group(self, index):
        id_role = QtCore.Qt.UserRole + 1
        source_index = self.perforce_proxy_model.mapToSource(index)
        if source_index.isValid():
            id = source_index.data(id_role)
            if id:
                id = int(id)
                self._setup_column_details_panel(id)

    # -----------------------------------------------------------------------
    # Column view model actions (emit signal for AppDialog to route)
    # -----------------------------------------------------------------------

    def _on_column_model_action(self, action):
        """Collects selected items and emits column_view_action_requested signal."""
        selected_items = []
        selected_files_to_revert = []
        selected_files_to_sync = []

        selected_indexes = self.ui.column_view.selectionModel().selectedRows()
        id_role = QtCore.Qt.UserRole + 1

        for selected_index in selected_indexes:
            source_index = self.perforce_proxy_model.mapToSource(selected_index)

            if self._set_groups:
                # Grouped mode: get id from custom role
                if not source_index.isValid():
                    continue
                id_val = source_index.data(id_role)
                if id_val is None:
                    continue
                id_val = int(id_val)
            else:
                # Ungrouped mode: get id from row data
                selected_row_data = self._get_row_data_from_source(source_index)
                id_val = 0
                if len(selected_row_data) >= 15:
                    id_val = int(selected_row_data[14])

            sg_item = self._column_view_dict.get(id_val, None)
            if not sg_item:
                continue

            if "path" not in sg_item:
                continue
            if "local_path" not in sg_item["path"]:
                continue

            target_file = sg_item["path"].get("local_path", None)
            depot_file = sg_item.get("depotFile", None)

            if action in ["add", "move/add", "edit", "delete"]:
                sg_item_action = sg_item.get("action", None)
                if sg_item_action and sg_item_action == "delete":
                    msg = "Cannot perform the action on the file {} as it has already been marked for deletion or is deleted.".format(depot_file)
                    self.log_message.emit(msg, 2)
                    continue
                if action == "delete":
                    msg = "Marking file {} for deletion ...".format(depot_file)
                else:
                    msg = "{} file {}".format(action, depot_file)
                self.log_message.emit(msg, 2)
                selected_items.append((sg_item, action))

            elif action == "revert":
                if target_file:
                    selected_files_to_revert.append(target_file)
                    msg = "Preparing to revert file {} ...".format(target_file)
                    self.log_message.emit(msg, 3)

            elif action == "sync":
                if target_file:
                    selected_files_to_sync.append(target_file)
                    msg = "Preparing to sync file {} ...".format(target_file)
                    self.log_message.emit(msg, 3)
                else:
                    msg = "Unable to sync file {} ...".format(target_file)
                    self.log_message.emit(msg, 3)

        # Emit signal so AppDialog can route to appropriate manager
        self.column_view_action_requested.emit(action, [
            {"action": action,
             "selected_items": selected_items,
             "files_to_revert": selected_files_to_revert,
             "files_to_sync": selected_files_to_sync}
        ])

    def _get_row_data_from_source(self, source_index):
        row_data = []
        if source_index.isValid():
            row_number = source_index.row()
            for col in range(self.column_view_model.columnCount()):
                item = source_index.model().item(row_number, col)
                if item:
                    row_data.append(item.text())
        logger.debug("Row data: {}".format(row_data))
        return row_data

    # -----------------------------------------------------------------------
    # Details pane
    # -----------------------------------------------------------------------

    def toggle_details_pane(self):
        if self.ui.details_tab.isVisible():
            self.set_details_pane_visibility(False)
        else:
            self.set_details_pane_visibility(True)

    def set_details_pane_visibility(self, visible):
        self._settings_manager.store("show_details", visible)
        if not visible:
            self._details_pane_visible = False
            self.ui.details_tab.setVisible(False)
            self.ui.info.setText("Show Details")
        else:
            self._details_pane_visible = True
            self.ui.details_tab.setVisible(True)
            self.ui.info.setText("Hide Details")
            selection_model = self.ui.publish_view.selectionModel()
            self.setup_file_details_panel(selection_model.selectedIndexes())

    # -----------------------------------------------------------------------
    # File details panel (main publish view)
    # -----------------------------------------------------------------------

    def setup_file_details_panel(self, items):
        from .model_latestpublish import SgLatestPublishModel

        def __make_table_row(left, right):
            return (
                "<tr><td><b style='color:#2C93E2'>%s</b>&nbsp;</td><td>%s</td></tr>"
                % (left, right)
            )

        def __set_publish_ui_visibility(is_publish):
            self.ui.version_file_history_label.setEnabled(is_publish)
            self.ui.file_history_view.setEnabled(is_publish)
            self.ui.file_detail_actions_btn.setVisible(is_publish)
            self.ui.file_detail_playback_btn.setVisible(is_publish)

        def __clear_publish_file_history(pixmap):
            self._publish_file_history_model.clear()
            self.ui.file_details_header.setText("")
            self.ui.file_details_image.setPixmap(pixmap)
            __set_publish_ui_visibility(False)

        if not self._details_pane_visible:
            return

        if len(items) == 0:
            __clear_publish_file_history(self._no_selection_pixmap)
        elif len(items) > 1:
            __clear_publish_file_history(self._multiple_publishes_pixmap)
        else:
            model_index = items[0]
            proxy_model = model_index.model()
            source_index = proxy_model.mapToSource(model_index)
            item = source_index.model().itemFromIndex(source_index)
            published_file_type = None
            sg_data = item.get_sg_data()
            if sg_data:
                published_file_type = sg_data.get('type', None)
            if published_file_type and published_file_type not in ['PublishedFile']:
                __clear_publish_file_history(self._no_selection_pixmap)
                return

            thumb_pixmap = item.icon().pixmap(512)
            self.ui.file_details_image.setPixmap(thumb_pixmap)

            if sg_data is None:
                folder_name = __make_table_row("Name", item.text())
                self.ui.file_details_header.setText("<table>%s</table>" % folder_name)
                __set_publish_ui_visibility(False)

            elif item.data(SgLatestPublishModel.IS_FOLDER_ROLE):
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
                desc_str = sg_data.get("description") or "No description entered."
                msg = ""
                display_name = shotgun_globals.get_type_display_name(sg_data["type"])
                msg += __make_table_row("Name", "%s %s" % (display_name, sg_data.get("code")))
                msg += __make_table_row("Status", status_name)
                msg += __make_table_row("Description", desc_str)
                self.ui.file_details_header.setText("<table>%s</table>" % msg)
                __set_publish_ui_visibility(False)
                self._publish_file_history_model.clear()

            else:
                __set_publish_ui_visibility(True)
                sg_item = item.get_sg_data()

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

                if sg_item.get("version"):
                    sg_url = sgtk.platform.current_bundle().shotgun.base_url
                    url = "%s/page/media_center?type=Version&id=%d" % (
                        sg_url, sg_item["version"]["id"])
                    self.ui.file_detail_playback_btn.setVisible(True)
                    self._current_version_detail_playback_url = url
                else:
                    self.ui.file_detail_playback_btn.setVisible(False)
                    self._current_version_detail_playback_url = None

                name_str = sg_item.get("name") or "No Name"
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
                        sg_item.get("entity").get("type"))
                    entity_str = "<b>%s</b> %s" % (
                        display_name, sg_item.get("entity").get("name"))
                    msg += __make_table_row("Link", entity_str)

                if sg_item.get("task"):
                    task_name_str = sg_item.get("task.Task.content") or "Unnamed"
                    if sg_item.get("task.Task.sg_status_list") is None:
                        task_status_str = "No Status"
                    else:
                        task_status_code = sg_item.get("task.Task.sg_status_list")
                        task_status_str = self._status_model.get_long_name(task_status_code)
                    msg += __make_table_row("Task", "%s (%s)" % (task_name_str, task_status_str))

                if sg_item.get("version.Version.sg_status_list"):
                    task_status_code = sg_item.get("version.Version.sg_status_list")
                    task_status_str = self._status_model.get_long_name(task_status_code)
                    msg += __make_table_row("Review", task_status_str)

                if sg_item.get("revision"):
                    msg += __make_table_row("Revision#", sg_item.get("revision"))

                if sg_item.get("action"):
                    msg += __make_table_row("Action", sg_item.get("action"))
                elif sg_item.get("headAction"):
                    msg += __make_table_row("Action", sg_item.get("headAction", "N/A"))

                self.ui.file_details_header.setText("<table>%s</table>" % msg)
                sg_data = item.get_sg_data()
                self._publish_file_history_model.load_data(sg_data)

            self.ui.file_details_header.updateGeometry()

    # -----------------------------------------------------------------------
    # Column details panel
    # -----------------------------------------------------------------------

    def _setup_column_details_panel(self, id):
        def __make_table_row(left, right):
            return (
                "<tr><td><b style='color:#2C93E2'>%s</b>&nbsp;</td><td>%s</td></tr>"
                % (left, right)
            )

        def __set_publish_ui_visibility(is_publish):
            self.ui.version_file_history_label.setEnabled(is_publish)
            self.ui.file_history_view.setEnabled(is_publish)
            self.ui.file_detail_actions_btn.setVisible(is_publish)
            self.ui.file_detail_playback_btn.setVisible(is_publish)

        def __clear_publish_file_history(pixmap):
            self._publish_file_history_model.clear()
            self.ui.file_details_header.setText("")
            self.ui.file_details_image.setPixmap(pixmap)
            __set_publish_ui_visibility(False)

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

            if self._publish_icons and id in self._publish_icons:
                thumb_pixmap = self._publish_icons[id].pixmap(512)
                self.ui.file_details_image.setPixmap(thumb_pixmap)

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

            if sg_item.get("version"):
                sg_url = sgtk.platform.current_bundle().shotgun.base_url
                url = "%s/page/media_center?type=Version&id=%d" % (
                    sg_url, sg_item["version"]["id"])
                self.ui.file_detail_playback_btn.setVisible(True)
                self._current_version_detail_playback_url = url
            else:
                self.ui.file_detail_playback_btn.setVisible(False)
                self._current_version_detail_playback_url = None

            name_str = sg_item.get("name") or "No Name"
            type_str = sg_item.get("type")
            msg = ""
            msg += __make_table_row("Name", name_str)
            msg += __make_table_row("Type", type_str)

            version = sg_item.get("version_number")
            vers_str = "%03d" % version if version is not None else "N/A"
            msg += __make_table_row("Version", "%s" % vers_str)

            if sg_item.get("entity"):
                display_name = shotgun_globals.get_type_display_name(
                    sg_item.get("entity").get("type"))
                entity_str = "<b>%s</b> %s" % (
                    display_name, sg_item.get("entity").get("name"))
                msg += __make_table_row("Link", entity_str)

            if sg_item.get("task"):
                task_name_str = sg_item.get("task.Task.content") or "Unnamed"
                if sg_item.get("task.Task.sg_status_list") is None:
                    task_status_str = "No Status"
                else:
                    task_status_code = sg_item.get("task.Task.sg_status_list")
                    task_status_str = self._status_model.get_long_name(task_status_code)
                msg += __make_table_row("Task", "%s (%s)" % (task_name_str, task_status_str))

            if sg_item.get("version.Version.sg_status_list"):
                task_status_code = sg_item.get("version.Version.sg_status_list")
                task_status_str = self._status_model.get_long_name(task_status_code)
                msg += __make_table_row("Review", task_status_str)

            if sg_item.get("revision"):
                msg += __make_table_row("Revision#", sg_item.get("revision"))

            if sg_item.get("action"):
                msg += __make_table_row("Action", sg_item.get("action"))
            elif sg_item.get("headAction"):
                msg += __make_table_row("Action", sg_item.get("headAction", "N/A"))

            self.ui.file_details_header.setText("<table>%s</table>" % msg)
            self._publish_file_history_model.load_data(sg_item)

        self.ui.file_details_header.updateGeometry()

    # -----------------------------------------------------------------------
    # Publish icons
    # -----------------------------------------------------------------------

    def _get_publish_icons(self):
        self._publish_icons = {}
        publish_model = self._publish_model
        if not publish_model:
            logger.warning("Cannot get publish icons: SgLatestPublishModel not available.")
            return

        id_to_source_index = {}
        for row in range(publish_model.rowCount()):
            source_index = publish_model.index(row, 0)
            item = publish_model.itemFromIndex(source_index)
            if item:
                sg_item = item.get_sg_data()
                if sg_item:
                    item_id = sg_item.get("id")
                    if item_id:
                        id_to_source_index[item_id] = source_index

        for item_key, sg_item_col_view in self._column_view_dict.items():
            item_id = sg_item_col_view.get("id") if sg_item_col_view else None
            source_index = id_to_source_index.get(item_id) if item_id else None
            if source_index:
                item = publish_model.itemFromIndex(source_index)
                if item:
                    icon = item.icon()
                    if icon and not icon.isNull():
                        self._publish_icons[item_key] = icon

        logger.debug(f"Collected {len(self._publish_icons)} icons.")

    # -----------------------------------------------------------------------
    # Publish view interaction (selection, double-click, context menu)
    # -----------------------------------------------------------------------

    @property
    def selected_publishes(self):
        selection_model = self.ui.file_history_view.selectionModel()
        if selection_model.hasSelection():
            proxy_index = selection_model.selection().indexes()[0]
            source_index = proxy_index.model().mapToSource(proxy_index)
            item = source_index.model().itemFromIndex(source_index)
            sg_data = item.get_sg_data()
            if sg_data:
                return [sg_data]

        sg_data_list = []
        selection_model = self.ui.publish_view.selectionModel()
        if selection_model.hasSelection():
            from .model_latestpublish import SgLatestPublishModel
            for proxy_index in selection_model.selection().indexes():
                source_index = proxy_index.model().mapToSource(proxy_index)
                item = source_index.model().itemFromIndex(source_index)
                sg_data = item.get_sg_data()
                if sg_data and not item.data(SgLatestPublishModel.IS_FOLDER_ROLE):
                    sg_data_list.append(sg_data)

        return sg_data_list

    def on_publish_selection(self, selected, deselected):
        selected_indexes = self.ui.publish_view.selectionModel().selectedIndexes()
        if len(selected_indexes) == 0:
            self.setup_file_details_panel([])
        else:
            self.setup_file_details_panel(selected_indexes)

    def on_publish_content_change(self):
        num_pub_items = self._publish_proxy_model.rowCount()
        if num_pub_items == 0:
            self._publish_main_overlay.show_message_pixmap(self._no_pubs_found_icon)
        else:
            self._publish_main_overlay.hide()

    def on_detail_version_playback(self):
        if self._current_version_detail_playback_url:
            QDesktopServices.openUrl(
                QUrl(self._current_version_detail_playback_url)
            )

    # -----------------------------------------------------------------------
    # Search / filter
    # -----------------------------------------------------------------------

    def on_column_view_set_search_query(self, search_filter):
        if self.main_view_mode == self.MAIN_VIEW_COLUMN:
            logger.debug("search_filter: {}".format(search_filter))
            if len(search_filter) > 1:
                self._column_view_search_filter = search_filter
            else:
                self._column_view_search_filter = None
            self._set_column_group()

    def on_publish_filter_clicked(self):
        if self.ui.search_publishes.isChecked():
            self.ui.search_publishes.setIcon(
                QIcon(QPixmap(":/res/search_active.png"))
            )
            self._search_widget.enable()
            if self.main_view_mode == self.MAIN_VIEW_COLUMN:
                logger.debug("Column view mode, search is active")
        else:
            self.ui.search_publishes.setIcon(
                QIcon(QPixmap(":/res/search.png"))
            )
            self._search_widget.disable()
            if self.main_view_mode == self.MAIN_VIEW_COLUMN:
                logger.debug("Column view mode, search is disabled")
                self._column_view_search_filter = None
                self._set_column_group()

    def set_search_widget(self, search_widget):
        """Set the search widget reference."""
        self._search_widget = search_widget

    def apply_type_filters_on_publishes(self):
        sg_type_ids = self._publish_type_model.get_selected_types()
        show_folders = self._publish_type_model.get_show_folders()
        self._publish_proxy_model.set_filter_by_type_ids(sg_type_ids, show_folders)

    # -----------------------------------------------------------------------
    # Thumb scaling
    # -----------------------------------------------------------------------

    def on_thumb_size_slider_change(self, value):
        self.ui.publish_view.setIconSize(QSize(value, value))
        self._settings_manager.store("thumb_size_scale", value)

    # -----------------------------------------------------------------------
    # Tooltip helper
    # -----------------------------------------------------------------------

    def _get_tooltip(self, data, sg_item):
        tooltip = ""
        if not sg_item or not data:
            return tooltip
        tooltip += "<b>Name:</b> %s" % (sg_item.get("code") or "No name given.")

        published_file_type = sg_item.get('type', None)
        if published_file_type in ['PublishedFile'] and data and len(data) >= 12:
            if sg_item.get("headAction"):
                tooltip += "<br><br><b>Head action:</b> %s" % (sg_item.get("headAction") or "N/A")
            if sg_item.get("action"):
                tooltip += "<br><br><b>Action:</b> %s" % (sg_item.get("action") or "N/A")
            tooltip += "<br><br><b>Revision:</b> #%s" % (sg_item.get("revision") or "N/A")
            tooltip += "<br><br><b>Size:</b> %s MB" % (sg_item.get("fileSize") or "0")
            tooltip += "<br><br><b>File Extension:</b> %s" % (data[6] or "N/A")
            tooltip += "<br><br><b>File Type:</b> %s" % (data[7] or "N/A")

            if not isinstance(sg_item.get("created_at"), datetime.datetime):
                created_unixtime = sg_item.get("created_at") or 0
                date_str = datetime.datetime.fromtimestamp(created_unixtime).strftime("%Y-%m-%d %H:%M")
            else:
                date_str = sg_item.get("created_at").strftime("%Y-%m-%d %H:%M")

            if sg_item.get("created_by") and sg_item["created_by"].get("name"):
                author_str = sg_item["created_by"].get("name")
            else:
                author_str = "Unspecified User"

            version = sg_item.get("version_number")
            vers_str = "%03d" % version if version is not None else "N/A"
            tooltip += "<br><br><b>Version:</b> %s by %s at %s" % (vers_str, author_str, date_str)

        tooltip += "<br><br><b>Task Name:</b> %s" % (data[9] or "N/A")
        tooltip += "<br><br><b>Task Status:</b> %s" % (data[10] or "N/A")
        tooltip += "<br><br><b>Path:</b> %s" % ((sg_item.get("path") or {}).get("local_path"))
        tooltip += "<br><br><b>Publish ID:</b> %s" % (sg_item.get("id") or "0")
        tooltip += "<br><br><b>Description:</b> %s" % (sg_item.get("description") or "No description given.")

        if sg_item.get("headChange"):
            tooltip += "<br><br><b>Head change:</b> %s" % (sg_item.get("headChange") or "N/A")
        if sg_item.get("change"):
            tooltip += "<br><br><b>Change:</b> %s" % (sg_item.get("change") or "N/A")
        if sg_item.get("entity"):
            entity = sg_item.get("entity")
            if entity:
                tooltip += "<br><br><b>Entity:</b> %s" % entity.get("name", "N/A")
                tooltip += "<br><br><b>Entity ID:</b> %s" % entity.get("id", "N/A")

        return tooltip

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
PublishIntegration — owns publishing workflows, pending/submitted views,
changelist operations, CLI submission, fix operations.

Extracted from dialog.py as Phase 3, Step 3 of the P4SG cleanup.
"""

import os
import re
import time
import threading
from os.path import expanduser
from collections import defaultdict, OrderedDict

import sgtk
from sgtk.util import login
from sgtk.platform.qt import QtCore, QtGui

# Import Qt classes into module namespace (mirrors dialog.py pattern)
for _name, _cls in QtCore.__dict__.items():
    if isinstance(_cls, type):
        globals()[_name] = _cls
for _name, _cls in QtGui.__dict__.items():
    if isinstance(_cls, type):
        globals()[_name] = _cls

from . import constants
from .publish_item import PublishItem
from .perforce_change import (
    create_change, add_to_change, submit_change,
    submit_and_delete_file, submit_single_file, submit_and_delete_file_list,
)
from .treeview_widget import TreeViewWidget, SWCTreeView
from .submit_changelist_widget import SubmitChangelistWidget
from .changelist_selection_operation import ChangelistSelection
from .date_time import create_publish_timestamp
from .utils import (
    check_validity_by_path_parts, check_validity_by_published_file,
    local_to_depot,
)

logger = sgtk.platform.get_logger(__name__)

# Import frameworks needed by this module
shotgun_model = sgtk.platform.import_framework(
    "tk-swc-framework-shotgunutils", "shotgun_model"
)
swc_fw = sgtk.platform.import_framework(
    "tk-framework-swc", "Context_Utils"
)


class PublishIntegration(QtCore.QObject):
    """
    Manages publishing workflows, pending/submitted views, changelist
    operations, CLI submission, and fix operations.
    """

    # Signals
    log_message = QtCore.Signal(str, int)

    def __init__(self, app, ui, sync_manager, parent=None):
        super(PublishIntegration, self).__init__(parent)
        self._app = app
        self.ui = ui
        self._sync_manager = sync_manager

        # P4 connection (from sync_manager)
        self._p4 = sync_manager.p4

        # Constants
        self.settings = constants.EXTENSION_TYPE_MAP
        self.action_dict = constants.ACTION_MAP
        self.status_dict = constants.STATUS_MAP

        # Changelist data
        self._change_dict = {}

        # fstat data
        self._fstat_dict = {}
        self._submitted_changes = {}

        # Publish data
        self._sg_data = []
        self._submitted_data_to_publish = []
        self._pending_data_to_publish = []
        self._action_data_to_publish = []
        self._submitted_publish_list = []
        self._pending_publish_list = []

        # Item path dict (populated by _get_perforce_data)
        self._item_path_dict = defaultdict(int)

        # Entity path (set externally)
        self._entity_path = None

        # Pending view state
        self.pending_tree_view = None
        self._pending_view_widget = None
        self._pending_view_model = None

        # Submitted view state
        self.submitted_tree_view = None

        # Submit widget state
        self._submit_widget_dict = {}
        self.change_sg_item = None
        self.submitter_widget = None

        # Publisher directory
        self._home_dir = None
        self._publish_files_path = None
        self._publish_files_description = None
        self._publisher_is_closed_path = None
        self._create_publisher_dir()

        # Callbacks set externally
        self._get_selected_entity_fn = None
        self._load_publishes_for_entity_item_fn = None
        self._get_entity_info_fn = None
        self._create_key_fn = None
        self._convert_local_to_depot_fn = None
        self._add_log_fn = None
        self._reload_treeview_fn = None
        self._on_treeview_item_selected_fn = None
        self._setup_file_details_panel_fn = None
        self._do_sync_files_fn = None
        self._refresh_publish_data_fn = None
        self._publish_model = None

    # -----------------------------------------------------------------------
    # Setters for deferred initialization
    # -----------------------------------------------------------------------

    def set_callbacks(self,
                      get_selected_entity_fn,
                      load_publishes_for_entity_item_fn,
                      get_entity_info_fn,
                      create_key_fn,
                      convert_local_to_depot_fn,
                      add_log_fn,
                      reload_treeview_fn=None,
                      on_treeview_item_selected_fn=None,
                      setup_file_details_panel_fn=None,
                      do_sync_files_fn=None,
                      refresh_publish_data_fn=None):
        self._get_selected_entity_fn = get_selected_entity_fn
        self._load_publishes_for_entity_item_fn = load_publishes_for_entity_item_fn
        self._get_entity_info_fn = get_entity_info_fn
        self._create_key_fn = create_key_fn
        self._convert_local_to_depot_fn = convert_local_to_depot_fn
        self._add_log_fn = add_log_fn
        self._reload_treeview_fn = reload_treeview_fn
        self._on_treeview_item_selected_fn = on_treeview_item_selected_fn
        self._setup_file_details_panel_fn = setup_file_details_panel_fn
        self._do_sync_files_fn = do_sync_files_fn
        self._refresh_publish_data_fn = refresh_publish_data_fn

    def set_publish_model(self, publish_model, SgLatestPublishModel):
        self._publish_model = publish_model
        self._SgLatestPublishModel = SgLatestPublishModel

    def set_entity_path(self, entity_path):
        self._entity_path = entity_path

    def set_sg_data(self, sg_data):
        self._sg_data = sg_data

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _add_log(self, msg, level=2):
        if self._add_log_fn:
            self._add_log_fn(msg, level)
        else:
            self.log_message.emit(msg, level)

    def _create_key(self, file_path):
        return self._create_key_fn(file_path)

    def _convert_local_to_depot(self, local_path):
        return self._convert_local_to_depot_fn(local_path)

    def _get_selected_entity(self):
        return self._get_selected_entity_fn()

    def _get_entity_info(self, entity_data):
        return self._get_entity_info_fn(entity_data)

    # -----------------------------------------------------------------------
    # Publisher directory
    # -----------------------------------------------------------------------

    def _create_publisher_dir(self):
        home_dir = expanduser("~")
        self._home_dir = "{}/.publisher".format(home_dir)
        if not os.path.exists(self._home_dir):
            os.makedirs(self._home_dir)
        self._publish_files_path = "{}/publish_files.txt".format(self._home_dir)
        self._publish_files_description = "{}/publish_files_description.txt".format(self._home_dir)
        self._publisher_is_closed_path = "{}/publisher_is_closed.txt".format(self._home_dir)

    # -----------------------------------------------------------------------
    # Changelist operations
    # -----------------------------------------------------------------------

    def _get_default_change(self):
        max_retries = 3
        default_changelist = None
        try:
            for attempt in range(max_retries):
                default_changelist = self._p4.fetch_change()
                if not default_changelist:
                    time.sleep(0.5)
                    continue
                else:
                    break
        except:
            pass
        return default_changelist

    def _get_default_changelists(self):
        key = "default"
        self._change_dict[key] = []
        default_changelist = self._get_default_change()
        if not default_changelist:
            logger.debug("<<<<<<<  Unable to get default changelist")
            return

        sg_item = {}
        sg_item['changeListInfo'] = True
        sg_item['headTime'] = default_changelist.get('time', None)
        sg_item['p4_user'] = default_changelist.get('User', None)
        description = default_changelist.get('Description', None)
        if not description or "description" in description:
            description = "Default Changelist"
        sg_item['description'] = description
        self._change_dict[key].append(sg_item)

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
                            file_path = sg_item.get("clientFile", None)
                            if file_path:
                                sg_item["path"] = {}
                                sg_item["path"]["local_path"] = file_path
                            have_rev = sg_item.get('haveRev', "0")
                            head_rev = sg_item.get('headRev', "0")
                            if not have_rev or have_rev == "none":
                                have_rev = "0"
                            sg_item["revision"] = "#{}/{}".format(have_rev, head_rev)
                            sg_item["action"] = sg_item.get("action", None) or sg_item.get("headAction", None)
                            p4_status = self._get_action(sg_item)
                            self._change_dict[key].append(sg_item)

    def _get_pending_changelists(self):
        client = self._sync_manager.get_client_name()
        if not client:
            logger.debug("<<<<<<<  Unable to get client")
            return

        workspace = client.get("Client", None)
        change_lists = self._sync_manager.get_change_lists(workspace)
        if not change_lists:
            logger.debug("<<<<<<<  Unable to get pending changelists")
            return

        for change_list in change_lists:
            key = change_list.get("change", None)
            desc_files = self._sync_manager.get_desc_files(key)

            if desc_files:
                for desc in desc_files:
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
                        self._change_dict[key].append(sg_item)

                        files_rev = desc.get('rev', None)
                        files_action = desc.get('action', None)
                        change_file_info = zip(depot_files, files_rev, files_action)

                        for depot_file, rev, action in change_file_info:
                            if depot_file:
                                fstat_list = self._sync_manager.get_fstat_list(depot_file)
                                if fstat_list:
                                    fstat = fstat_list[0]
                                    client_file = self._sync_manager.get_client_file(depot_file)
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

    def _get_change_dictionary(self, data_dict):
        """
        Creates dictionary for every changelist and all its depot files.
        key: changelist number
        value: sorted list of depotfiles
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
        return change_dict_sorted

    def _get_action(self, sg_item):
        """Get action from sg_item."""
        action = sg_item.get("action", None)
        if not action:
            action = sg_item.get("headAction", None)
        return action

    # -----------------------------------------------------------------------
    # Pending view
    # -----------------------------------------------------------------------

    def populate_pending_widget(self):
        msg = "\n <span style='color:#2C93E2'>Populating the pending view. Please wait...</span> \n"
        self._add_log(msg, 2)

        self._change_dict = {}
        self._get_default_changelists()
        self._get_pending_changelists()

        self.pending_tree_view = TreeViewWidget(
            data_dict=self._change_dict, sorted=True, mode="pending",
            p4=self._p4, parent=self.parent()
        )
        self.pending_tree_view.set_mode()
        self.pending_tree_view.single_selection()
        self.pending_tree_view.populate_treeview_widget_pending()
        self._pending_view_widget = self.pending_tree_view.get_treeview_widget()

        # Create a container widget for the TreeView
        container_widget = QWidget()
        container_layout = QVBoxLayout(container_widget)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self._pending_view_widget = self.pending_tree_view.get_treeview_widget()
        self.pending_tree_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_layout.addWidget(self._pending_view_widget)
        container_layout.addStretch()

        self.ui.pending_scroll.setWidget(container_widget)
        self.ui.pending_scroll.setWidgetResizable(True)
        self.ui.pending_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ui.pending_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._pending_view_model = self.pending_tree_view.proxymodel
        self._create_pending_view_context_menu()

        msg = "\n <span style='color:#2C93E2'> Right-click on a file to 'Publish...' the changelist in Shotgrid or 'Revert' it in Perforce.</span> \n"
        self._add_log(msg, 2)
        self.ui.sync_files.setEnabled(False)
        self.ui.sync_parents.setEnabled(False)
        self.ui.fix_selected.setEnabled(False)
        self.ui.fix_all.setEnabled(False)
        self.ui.submit_files.setEnabled(True)

    def update_pending_view(self):
        """Shows the pending view."""
        self._change_dict = {}
        self._get_default_changelists()
        self._get_pending_changelists()

        self.pending_tree_view = TreeViewWidget(
            data_dict=self._change_dict, sorted=True, mode="pending", p4=self._p4
        )
        self.pending_tree_view.populate_treeview_widget_pending()
        publish_widget = self.pending_tree_view.get_treeview_widget()
        self.ui.pending_scroll.setWidget(publish_widget)

    def _create_pending_view_context_menu(self):
        self._pending_view_publish_action = QAction("Publish...", self._pending_view_widget)
        self._pending_view_publish_action.triggered.connect(
            lambda: self._on_pending_view_model_action("publish")
        )

        self._pending_view_submit_action = QAction("Submit...", self._pending_view_widget)
        self._pending_view_submit_action.triggered.connect(self._on_submit_files)

        self._pending_view_revert_action = QAction("Revert", self._pending_view_widget)
        self._pending_view_revert_action.triggered.connect(
            lambda: self._on_pending_view_model_action("revert")
        )
        self._pending_view_move_action = QAction("Move to Changelist", self._pending_view_widget)
        self._pending_view_move_action.triggered.connect(
            lambda: self._on_pending_view_model_action("move")
        )

        self._pending_view_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self._pending_view_widget.customContextMenuRequested.connect(
            self._show_pending_view_actions
        )

    def _show_pending_view_actions(self, pos):
        """Shows the actions for the current pending view selection."""
        index = self._pending_view_widget.indexAt(pos)
        if not index.isValid():
            return

        is_parent = not index.parent().isValid()

        menu = QMenu(self.parent())
        if is_parent:
            menu.addAction(self._pending_view_publish_action)
            menu.addAction(self._pending_view_submit_action)
        else:
            menu.addAction(self._pending_view_revert_action)
            menu.addSeparator()
            menu.addAction(self._pending_view_move_action)

        menu.addSeparator()

        global_pos = self._pending_view_widget.mapToGlobal(pos)
        event_loop = QEventLoop()
        menu.aboutToHide.connect(event_loop.quit)
        menu.exec_(global_pos)
        event_loop.exec_()

    def _on_pending_view_model_action(self, action):
        selected_files_to_revert = []
        selected_files_to_delete = []
        selected_actions_to_move = []
        selected_files_to_move = []
        engine = sgtk.platform.current_engine()

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
                result, error_list = self._validate_changelist_files_with_threads(files_in_changelist)

                if not result:
                    msg = "\n <span style='color:#CC3333'>The following files in the changelist {} are not linked to any Shotgrid entity:</span> \n".format(change)
                    self._add_log(msg, 2)
                    for filepath in error_list:
                        msg = "\n <span style='color:#CC3333'>{}</span> \n".format(filepath)
                        self._add_log(msg, 2)
                    return

            try:
                try:
                    self._create_description_file(files_in_changelist, description)
                except:
                    pass
                logger.debug("change is: {}".format(change))
                engine = sgtk.platform.current_engine()
                if engine:
                    app_command = engine.commands.get("Publish...")
                    if app_command:
                        logger.debug("Pass in the desired changelist parameter: {}".format(change))
                        app_command["callback"](change)
            except Exception as e:
                logger.debug("Error loading publisher: {}".format(e))

        if action == "revert" and selected_indexes:
            for selected_index in selected_indexes:
                try:
                    source_index = self._pending_view_model.mapToSource(selected_index)
                    selected_row_data = self._get_pending_data_from_source(source_index)
                    action = self._get_action_data_from_source(source_index)
                    change = self._get_change_data_from_source(source_index)
                    if selected_row_data:
                        target_file = selected_row_data.split("#")[0]
                        target_file = target_file.strip()
                        logger.debug("Revert: Target file {target_file}")
                        selected_files_to_revert.append(target_file)
                except Exception as e:
                    logger.debug("Error processing selection: {}".format(e))
            if selected_files_to_revert:
                files_str = "\n".join(selected_files_to_revert)
                logger.debug("Revert: files_str {files_str}")
                reply = QMessageBox.question(
                    self.parent(), 'Confirmation',
                    f"Are you sure you want to revert the following files?\n\n{files_str}",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
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
                files_str = "\n".join(selected_files_to_revert)
                reply = QMessageBox.question(
                    self.parent(), 'Confirmation',
                    f"Are you sure you want to delete the following files?\n\n{files_str}",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._delete_pending_data(selected_files_to_revert)

        if action == "move" and selected_indexes:
            logger.debug("Move files to a different changelist")
            for selected_index in selected_indexes:
                try:
                    source_index = self._pending_view_model.mapToSource(selected_index)
                    selected_row_data = self._get_pending_data_from_source(source_index)
                    change = self._get_change_data_from_source(source_index)
                    if selected_row_data:
                        action = self._get_action_data_from_source(source_index)
                        sg_item = self._get_sg_data_from_source(source_index)
                        selected_actions_to_move.append((sg_item, action))
                        target_file = sg_item.get("depotFile", None)
                        if not target_file:
                            if "path" in sg_item:
                                if "local_path" in sg_item["path"]:
                                    target_file = sg_item["path"].get("local_path", None)
                        if target_file:
                            selected_files_to_move.append(target_file)
                except Exception as e:
                    logger.debug("Error processing selection: {}".format(e))
            if selected_files_to_move:
                files_str = "\n".join(selected_files_to_move)
                reply = QMessageBox.question(
                    self.parent(), 'Confirmation',
                    f"Do you wish to transfer the selected files to a new changelist?\n\n{files_str}",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    try:
                        if selected_actions_to_move:
                            self.perform_changelist_selection(selected_actions_to_move)
                    except Exception as e:
                        logger.debug("Unable to revert file: {}, Error: {}".format(target_file, e))

        if selected_files_to_revert or selected_files_to_delete or selected_files_to_move:
            self.populate_pending_widget()

    # -----------------------------------------------------------------------
    # Pending view data extraction helpers
    # -----------------------------------------------------------------------

    def _get_pending_data_from_source(self, source_index):
        if source_index.isValid():
            parent_item = source_index.model().itemFromIndex(source_index.parent())
            if parent_item:
                child_item = parent_item.child(source_index.row(), 0)
            else:
                child_item = source_index.model().item(source_index.row(), 0)
            if child_item:
                return child_item.text()
        return None

    def _get_action_data_from_source(self, source_index):
        if source_index.isValid():
            id_role = QtCore.Qt.UserRole + 1
            action = source_index.data(id_role)
            return action
        return None

    def _get_change_data_from_source(self, source_index):
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
        try:
            if source_index.isValid():
                id_role = QtCore.Qt.UserRole + 3
                sg_item = source_index.data(id_role)
                return sg_item
        except Exception as e:
            logger.debug("Error getting sg_data from source: {}".format(e))
        return None

    def _get_pending_info_from_source(self, source_index):
        if source_index.isValid():
            parent_item = source_index.model().itemFromIndex(source_index)
            if parent_item:
                change_text = parent_item.text()
                if change_text:
                    parts = change_text.split(" - ")
                    if len(parts) >= 2:
                        change = parts[0].strip()
                        description = parts[1].strip()
                        if change and change != "default":
                            change = int(change)
                        return change, description
        return 0, ""

    # -----------------------------------------------------------------------
    # Changelist validation
    # -----------------------------------------------------------------------

    def _list_files_in_changelist(self, change):
        try:
            p4_result = self._p4.run("describe", "-s", str(change))
            logger.debug("p4_result for {change}: {p4_result}")
            files_in_changelist = []
            for depot_file in p4_result[0]["depotFile"]:
                client_file = self._sync_manager.get_client_file(depot_file)
                files_in_changelist.append(client_file)
            return files_in_changelist
        except Exception as e:
            logger.debug("Error listing files in changelist {}: {}".format(change, e))
            return []

    def _validate_changelist_files(self, files_in_changelist):
        """Validate changelist files."""
        error_list = []
        for filepath in files_in_changelist:
            sg_item = {}
            sg_item["path"] = {}
            sg_item["path"]["local_path"] = filepath
            entity, published_file = self.get_entity_from_sg_item(sg_item)
            if not entity:
                error_list.append(filepath)
                logger.debug("_validate_changelist_files: error_list: {}".format(error_list))
        if error_list and len(error_list) > 0:
            return False, error_list
        else:
            return True, error_list

    def _validate_changelist_files_with_threads(self, files_in_changelist):
        """Validate changelist files using threading for faster execution."""
        num_threads = max(1, os.cpu_count() or 1)
        files_per_thread = len(files_in_changelist) // num_threads
        error_list = []
        results = []

        def validate_files_sublist(files_sublist):
            result, errors = self._validate_changelist_files(files_sublist)
            results.append(result)
            error_list.extend(errors)

        threads = []
        for i in range(num_threads):
            start_index = i * files_per_thread
            end_index = start_index + files_per_thread
            if i == num_threads - 1:
                end_index = len(files_in_changelist)
            files_sublist = files_in_changelist[start_index:end_index]
            thread = threading.Thread(target=validate_files_sublist, args=(files_sublist,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        overall_result = all(results)
        return overall_result, error_list

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

    # -----------------------------------------------------------------------
    # Submitted view
    # -----------------------------------------------------------------------

    def populate_submitted_widget(self):
        self.ui.submitted_scroll.setVisible(True)
        self._reset_submitted_widget()
        msg = "\n <span style='color:#2C93E2'>Updating data ...</span> \n"
        self._add_log(msg, 2)
        self._update_fstat_data()
        self._fix_fstat_dict()

        length = len(self._fstat_dict)
        if length > 0:
            msg = "\n <span style='color:#2C93E2'>Populating the submitted view with {} files. Please wait...</span> \n".format(
                length)
            self._add_log(msg, 2)
            self.submitted_tree_view = TreeViewWidget(
                data_dict=self._fstat_dict, sorted=False, mode="submitted", p4=self._p4
            )
            self.submitted_tree_view.populate_treeview_widget_submitted()
            publish_widget = self.submitted_tree_view.get_treeview_widget()
            self.ui.submitted_scroll.setWidget(publish_widget)

            msg = "\n <span style='color:#2C93E2'>Select files in the Submitted view then click <i>Fix Selected</i> or click <i>Fix All</i> to publish them using the <i>Shotgrid Publisher</i>...</span> \n"
            self._add_log(msg, 2)

    def _reset_submitted_widget(self):
        null_widget = SWCTreeView()
        self.ui.submitted_scroll.setWidget(null_widget)

    # -----------------------------------------------------------------------
    # Submit files
    # -----------------------------------------------------------------------

    def _on_submit_files(self):
        """When someone clicks on the 'Submit Files' button."""
        self.change_sg_item = self._get_submit_changelist_widget_data()
        if self.change_sg_item and self._submit_widget_dict:
            self.submitter_widget = SubmitChangelistWidget(
                parent=self.parent(), myp4=self._p4,
                change_item=self.change_sg_item, file_dict=self._submit_widget_dict
            )
            self.submitter_widget.show()
        else:
            msg = "\n <span style='color:#2C93E2'>No files selected for submission.</span> \n"
            self._add_log(msg, 2)

    def _get_submit_changelist_widget_data(self):
        """Extract data for submit changelist widget."""
        selected_indexes = self._pending_view_widget.selectionModel().selectedRows()
        selected_depot_files = []
        self._submit_widget_dict = {}
        change_sg_item = None

        for selected_index in selected_indexes:
            try:
                source_index = self._pending_view_model.mapToSource(selected_index)
                change = self._get_change_data_from_source(source_index)
                logger.debug("-----------------------------------------------")
                logger.debug(">>>>>>>>>>> change:{}".format(change))
                change_key = str(change)
                children = self._change_dict.get(change_key, None)
                logger.debug(">>>>>>>>>>>change dict:")
                for k, v in self._change_dict.items():
                    logger.debug("Change:{} values:{}".format(k, v))

                if children:
                    for sg_item in children:
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

        logger.debug(">>>>>>>>>>>_submit_widget_dict dict:")
        for k, v in self._submit_widget_dict.items():
            logger.debug("Change:{} values:{}".format(k, v))
        return change_sg_item

    def _extract_file_info(self, target_file):
        """Get file name, extension and folder."""
        file_name = os.path.basename(target_file)
        folder = os.path.dirname(target_file)
        extension = os.path.splitext(file_name)[1]
        extension = extension[1:] if extension else "N/A"
        type = self.settings.get(extension, "N/A")
        return file_name, folder, type

    def _on_submit_changelist(self, submitter_widget):
        """Callback for the submit button in the SubmitChangelistWidget."""
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

        print(f"Submitting changelist with description: {description}")
        print("Files to be submitted:")
        for file_info in selected_files:
            print(f"- {file_info}")

        submitter_widget.accept()

    def on_submit_deleted_files(self, change_sg_item, file_info_deleted):
        """Handle submit of deleted files."""
        selected_files_to_delete = []
        selected_tuples_to_delete = []
        selected_tuples_to_publish = []
        change = change_sg_item.get("change", None)
        for file_info in file_info_deleted:
            target_file = None
            try:
                action = file_info.get("pending_action", None)
                sg_item = file_info.get("sg_item", None)
                if sg_item:
                    target_file = sg_item.get("depotFile", None)
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
            files_str = "\n".join(selected_files_to_delete)
            reply = QMessageBox.question(
                self.parent(), 'Confirmation',
                f"Are you sure you want to delete the following files in Perforce?\n\n{files_str}",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                msg = "\n <span style='color:#2C93E2'>Submitting pending files for deletion in Perforce...</span> \n"
                self._add_log(msg, 2)
                if selected_files_to_delete:
                    self._publish_pending_data_using_command_line(selected_tuples_to_publish)
                    self._delete_pending_data(selected_tuples_to_delete)
                msg = "\n <span style='color:#2C93E2'>Updating the Pending view ...</span> \n"
                self._add_log(msg, 2)
        else:
            msg = "\n <span style='color:#2C93E2'>Please select files marked for deletion in the Pending view...</span> \n"
            self._add_log(msg, 2)

    def on_submit_other_files(self, change_sg_item, file_info_other):
        """Handle submit of non-deleted files."""
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

    # -----------------------------------------------------------------------
    # Publishing (pending data)
    # -----------------------------------------------------------------------

    def _publish_pending_data_using_command_line(self, selected_tuples_to_publish):
        """Publish Depot Data using threading for speedup."""
        logger.debug(">>>>>>>>>>>  _publish_pending_data_using_command_line")
        logger.debug(">>>>>>>>>>>  selected_tuples_to_publish:{}".format(selected_tuples_to_publish))
        if selected_tuples_to_publish:
            msg = "\n <span style='color:#2C93E2'>Publishing pending files in Shotgrid</span> \n"
            self._add_log(msg, 2)

            threads = []
            for change, target_file, action, sg_item in selected_tuples_to_publish:
                thread = threading.Thread(
                    target=self._publish_file_thread,
                    args=(change, target_file, action, sg_item, self._add_log,
                          self.get_entity_from_sg_item)
                )
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            msg = "\n <span style='color:#2C93E2'>Publishing files is complete</span> \n"
            self._add_log(msg, 2)
        else:
            msg = "\n <span style='color:#2C93E2'>No need to publish any file</span> \n"
            self._add_log(msg, 2)

    def _publish_file_thread(self, change, target_file, action, sg_item, log_callback, get_entity_callback):
        """Function to publish a file in a separate thread."""
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

    def get_entity_from_sg_item(self, sg_item):
        """Check if the filepath leads to a valid shotgrid entity."""
        filepath = sg_item.get("path", {}).get("local_path", "N/A")
        entity, published_file = None, None

        try:
            entity, published_file = check_validity_by_published_file(sg_item)
            logger.debug(
                f"get_entity_from_sg_item: check_validity_by_published_file result - Entity: {entity}, PublishedFile: {published_file}")
        except Exception as e:
            logger.error(f"get_entity_from_sg_item: Error during check_validity_by_published_file: {e}", exc_info=True)

        if not entity:
            logger.debug(
                f"get_entity_from_sg_item: PublishedFile check failed or returned no entity. Attempting check_validity_by_path_parts...")
            try:
                entity, published_file = check_validity_by_path_parts(swc_fw, sg_item)
                logger.debug(
                    f"get_entity_from_sg_item: check_validity_by_path_parts result - Entity: {entity}, PublishedFile: {published_file}")
            except Exception as e:
                logger.error(f"get_entity_from_sg_item: Error during check_validity_by_path_parts: {e}", exc_info=True)

        if entity:
            logger.info(f"get_entity_from_sg_item: Successfully found Entity: {entity} for path: {filepath}")
        else:
            logger.warning(f"get_entity_from_sg_item: Failed to find Entity for path: {filepath}")

        return entity, published_file

    # -----------------------------------------------------------------------
    # Delete/submit operations
    # -----------------------------------------------------------------------

    def _delete_file_thread(self, change, file_to_submit, log_callback):
        """Function to delete a file in a separate thread.

        Creates its own P4 connection per Perforce threading requirements.
        """
        thread_p4 = None
        try:
            thread_p4 = self._sync_manager.create_thread_connection()
            submit_result, perforce_msg = submit_and_delete_file(thread_p4, change, file_to_submit)
            if submit_result and not perforce_msg:
                log_callback(f"File deleted from Perforce: {file_to_submit}", 2)
            else:
                log_callback(f"Error deleting file {file_to_submit}: {perforce_msg}", 4)
        except Exception as e:
            log_callback(f"Error deleting file {file_to_submit}: {str(e)}", 4)
        finally:
            if thread_p4:
                try:
                    thread_p4.disconnect()
                except Exception:
                    pass

    def _delete_pending_data(self, selected_tuples_to_delete):
        """Delete Depot Data in the Pending view that needs to be deleted."""
        if selected_tuples_to_delete:
            msg = "\n <span style='color:#2C93E2'>Submitting files for deletion...</span> \n"
            self._add_log(msg, 2)

            threads = []
            for change, file_to_submit in selected_tuples_to_delete:
                thread = threading.Thread(
                    target=self._delete_file_thread,
                    args=(change, file_to_submit, self._add_log)
                )
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            msg = "\n <span style='color:#2C93E2'>File deletion completed.</span> \n"
            self._add_log(msg, 2)

    def _submit_other_pending_data(self, selected_data_to_submit):
        """Publish Depot Data in the Pending view that are not marked for deletion."""
        if selected_data_to_submit:
            msg = "\n <span style='color:#2C93E2'>Submitting other pending files...</span> \n"
            self._add_log(msg, 2)

            for change, file_to_submit, action, sg_item in selected_data_to_submit:
                if change and file_to_submit and action:
                    if action not in ["delete"]:
                        msg = "{}".format(file_to_submit)
                        self._add_log(msg, 4)
                        submit_res = submit_single_file(self._p4, change, file_to_submit, action)
                        logger.debug("Result of submitting files: {}".format(submit_res))
                        if submit_res:
                            msg = "\n <span style='color:#2C93E2'>File submitted to Perforce:</span> \n".format(file_to_submit)
                            self._add_log(msg, 2)

    def _delete_pending_file(self, change, target_file):
        try:
            p4_result = self._p4.run("delete", target_file)
            submit_del_res = submit_change(self._p4, change, target_file)
            logger.debug("p4_result for {target_file}: {submit_del_res}")
        except Exception as e:
            logger.debug("Unable to delete file: {}, Error: {}".format(target_file, e))

    # -----------------------------------------------------------------------
    # Publishing (other pending data via Publisher UI)
    # -----------------------------------------------------------------------

    def _publish_other_pending_data(self, other_data_to_publish):
        """Publish Depot Data in the Pending view that does not need to be deleted."""
        if other_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Submitting pending files that are not marked for delete...</span> \n"
            self._add_log(msg, 2)
            out_file = open(self._publish_files_path, 'w')
            out_file.write('Pending Files\n')

            for key in other_data_to_publish:
                for sg_item in other_data_to_publish[key]:
                    if sg_item and 'path' in sg_item:
                        file_to_submit = sg_item['path'].get('local_path', None)
                        if file_to_submit:
                            msg = "{}".format(file_to_submit)
                            self._add_log(msg, 4)
                            out_file.write('%s\n' % file_to_submit)

            out_file.close()

            msg = "\n <span style='color:#2C93E2'>Initializing Publisher UI, please stand by...</span> \n"
            self._add_log(msg, 2)

            engine = sgtk.platform.current_engine()
            engine.commands["Publish..."]["callback"]()

            msg = "\n <span style='color:#2C93E2'>Updating the Pending View ...</span> \n"
            self._add_log(msg, 2)
            self.update_pending_view()

    def _publish_delete_pending_data(self, deleted_data_to_publish):
        """Publish Depot Data in the Pending view that needs to be deleted."""
        files_to_delete = []
        if deleted_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Submitting files for deletion...</span> \n"
            self._add_log(msg, 2)
            for key in deleted_data_to_publish:
                for sg_item in deleted_data_to_publish[key]:
                    file_to_submit = sg_item.get('path', {}).get('local_path', None) if 'path' in sg_item else None
                    if file_to_submit:
                        msg = "{}".format(file_to_submit)
                        self._add_log(msg, 4)
                        submit_del_res = submit_change(self._p4, file_to_submit)
                        logger.debug("Result of deleting files: {}".format(submit_del_res))
                        if submit_del_res:
                            if isinstance(submit_del_res, list) and len(submit_del_res) > 0:
                                submit_del_res = submit_del_res[0]
                                if 'submittedChange' in submit_del_res:
                                    sg_item['submittedChange'] = submit_del_res['submittedChange']
                                    self._publish_deleted_data_using_command_line([sg_item])

            self._publish_deleted_data_using_command_line(deleted_data_to_publish)

    def _publish_deleted_data_using_command_line(self, deleted_data_to_publish):
        """Publish Pending view Depot Data that needs to be deleted using the command line."""
        if deleted_data_to_publish:
            threads = []
            for sg_item in deleted_data_to_publish:
                file_path = sg_item['path'].get('local_path', None) if 'path' in sg_item else None
                target_context = self._find_task_context(file_path)

                if target_context.entity and file_path:
                    sg_item["entity"] = target_context.entity
                    thread = threading.Thread(
                        target=self._delete_one_file_thread,
                        args=(sg_item, file_path)
                    )
                    threads.append(thread)
                    thread.start()

            for thread in threads:
                thread.join()

            msg = "\n <span style='color:#2C93E2'>Publishing files marked for delete is complete</span> \n"
            self._add_log(msg, 2)
        else:
            msg = "\n <span style='color:#2C93E2'>No need to publish any file that is marked for deletion</span> \n"
            self._add_log(msg, 2)

    def _delete_one_file_thread(self, sg_item, file_path):
        """Delete a single file in a thread."""
        publisher = PublishItem(sg_item)
        publish_result = publisher.commandline_publishing()
        if publish_result:
            logger.debug("New data is: {}".format(publish_result))

    # -----------------------------------------------------------------------
    # Fix / publish submitted data
    # -----------------------------------------------------------------------

    def on_fix_list(self):
        self._publish_submitted_data_using_command_line()
        if self._setup_file_details_panel_fn:
            self._setup_file_details_panel_fn([])
        if self._on_treeview_item_selected_fn:
            self._on_treeview_item_selected_fn()

    def on_fix_selected(self):
        """Send unpublished depot files in the submitted view to the Shotgrid Publisher."""
        self._submitted_data_to_publish = self.submitted_tree_view.get_selected_publish_items()
        self._publish_submitted_data_using_command_line()
        if self._setup_file_details_panel_fn:
            self._setup_file_details_panel_fn([])
        if self._on_treeview_item_selected_fn:
            self._on_treeview_item_selected_fn()

    def on_fix_all(self):
        """Send all unpublished depot files in the submitted view to the Shotgrid Publisher."""
        self._submitted_data_to_publish = []
        for key in self._fstat_dict:
            sg_item = self._fstat_dict[key]
            is_published = sg_item.get("Published", False)
            if not is_published:
                self._submitted_data_to_publish.append(sg_item)
        self._publish_submitted_data_using_command_line()
        if self._setup_file_details_panel_fn:
            self._setup_file_details_panel_fn([])
        if self._on_treeview_item_selected_fn:
            self._on_treeview_item_selected_fn()

    def _publish_submitted_data_using_publisher_ui(self):
        """Publish Depot Data using Publisher UI."""
        selected_item = self._get_selected_entity()
        sg_entity = shotgun_model.get_sg_data(selected_item)

        if self._submitted_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Sending the following unpublished files to the Shotgrid Publisher...</span> \n"
            self._add_log(msg, 2)
            out_file = open(self._publish_files_path, 'w')
            out_file.write('Depot Files\n')
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
                        if action:
                            action = self.action_dict.get(action, None)
                            add_res = add_to_change(self._p4, change, file_to_publish)
                            action_result = self._p4.run(action, "-c", change, "-v", file_to_publish)
            out_file.close()

            engine = sgtk.platform.current_engine()
            engine.commands["Publish..."]["callback"]()
            msg = "\n <span style='color:#2C93E2'>Reloading data ...</span> \n"
            self._add_log(msg, 2)
            if self._reload_treeview_fn:
                self._reload_treeview_fn()

            msg = "\n <span style='color:#2C93E2'>Updating the Pending View ...</span> \n"
            self._add_log(msg, 2)
            self.update_pending_view()
        else:
            msg = "\n <span style='color:#2C93E2'>Check files in the Pending view to publish using the Shotgrid Publisher</span> \n"
            self._add_log(msg, 2)

        self._submitted_data_to_publish = []

    def _publish_submitted_data_using_command_line(self):
        """Publish Depot Data using threading for speedup."""
        selected_item = self._get_selected_entity()
        sg_entity = shotgun_model.get_sg_data(selected_item)

        if self._submitted_data_to_publish:
            msg = "\n <span style='color:#2C93E2'>Publishing all unpublished files in the depot associated with this entity to Shotgrid ...</span> \n"
            self._add_log(msg, 2)
            files_count = len(self._submitted_data_to_publish)

            threads = []
            for i, sg_item in enumerate(self._submitted_data_to_publish):
                sg_item["entity"] = sg_entity
                if 'path' in sg_item:
                    rev = sg_item.get("version_number") or sg_item.get("headRev") or 1
                    file_to_publish = sg_item['path'].get('local_path', None)
                    msg = "({}/{})  Publishing file: {}#{}".format(i + 1, files_count, file_to_publish, rev)
                    self._add_log(msg, 4)

                    thread = threading.Thread(
                        target=self._publish_one_file_thread,
                        args=(sg_item, file_to_publish, rev)
                    )
                    threads.append(thread)
                    thread.start()

            for thread in threads:
                thread.join()

            msg = "\n <span style='color:#2C93E2'>Publishing files is complete</span> \n"
            self._add_log(msg, 2)
            msg = "\n <span style='color:#2C93E2'>Reloading data</span> \n"
            self._add_log(msg, 2)
        else:
            msg = "\n <span style='color:#2C93E2'>No need to publish any file</span> \n"
            self._add_log(msg, 2)

        self._submitted_data_to_publish = []

    def _publish_one_file_thread(self, sg_item, file_to_publish, rev):
        """Publish a single file in a thread."""
        publisher = PublishItem(sg_item)
        publish_result = publisher.commandline_publishing()
        if publish_result:
            logger.debug("New data is: {}".format(publish_result))

    # -----------------------------------------------------------------------
    # Publish files action
    # -----------------------------------------------------------------------

    def on_publish_files(self):
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

        self._action_data_to_publish = []

    # -----------------------------------------------------------------------
    # Publish model action (main publish view context menu)
    # -----------------------------------------------------------------------

    def on_publish_model_action(self, action):
        selected_actions = []
        selected_files_to_revert = []
        selected_files_to_sync = []
        selected_indexes = self.ui.publish_view.selectionModel().selectedIndexes()
        self._submitted_data_to_publish = []

        for model_index in selected_indexes:
            proxy_model = model_index.model()
            source_index = proxy_model.mapToSource(model_index)
            item = source_index.model().itemFromIndex(source_index)

            is_folder = item.data(self._SgLatestPublishModel.IS_FOLDER_ROLE)
            if not is_folder:
                sg_item = shotgun_model.get_sg_data(model_index)

                if sg_item and "path" in sg_item:
                    if "local_path" in sg_item["path"]:
                        target_file = sg_item["path"].get("local_path", None)
                        depot_file = sg_item.get("depotFile", None)
                        if action in ["fix"]:
                            published_file_type = sg_item.get("published_file_type", None)
                            is_sg_published_file_type = sg_item.get("type") == "PublishedFile"
                            if not published_file_type and not is_sg_published_file_type:
                                msg = "Fixing file {} ...".format(target_file)
                                self._add_log(msg, 3)
                                self._submitted_data_to_publish.append(sg_item)
                            else:
                                msg = "File {} is already considered published or is of a published type. 'Fix' not applicable.".format(
                                    target_file)
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
                            if target_file:
                                selected_files_to_revert.append(target_file)
                                msg = "Preparing to revert file {} ...".format(target_file)
                                self._add_log(msg, 3)

                        elif action == "sync":
                            if target_file:
                                selected_files_to_sync.append(target_file)
                                msg = "Preparing to sync file {} ...".format(target_file)
                                self._add_log(msg, 3)

        if self._submitted_data_to_publish:
            self.on_fix_list()

        if action == "revert" and selected_files_to_revert:
            try:
                msg = f"Reverting {len(selected_files_to_revert)} selected file(s)..."
                self._add_log(msg, 2)
                p4_result = self._p4.run("revert", *selected_files_to_revert)
                logger.debug(f"Bulk revert result: {p4_result}")
                if p4_result:
                    if self._refresh_publish_data_fn:
                        self._refresh_publish_data_fn()
            except Exception as e:
                logger.error(f"Error during bulk revert: {e}")
                self._add_log(f"Error during bulk revert: {e}", 2)

        if action == "sync" and selected_files_to_sync:
            try:
                msg = f"Syncing {len(selected_files_to_sync)} selected file(s)..."
                self._add_log(msg, 2)
                if self._do_sync_files_fn:
                    self._do_sync_files_fn(selected_files_to_sync)
                if self._refresh_publish_data_fn:
                    self._refresh_publish_data_fn()
                msg = f"Syncing of {len(selected_files_to_sync)} file(s) complete."
                self._add_log(msg, 2)
            except Exception as e:
                logger.error(f"Error during bulk sync: {e}")
                self._add_log(f"Error during bulk sync: {e}", 2)

        if selected_actions:
            self.perform_changelist_selection(selected_actions)
        self._publish_model.async_refresh()

    def perform_changelist_selection(self, selected_actions):
        perform_action = ChangelistSelection(self._p4, selected_actions=selected_actions, parent=self.parent())
        perform_action.show()

    # -----------------------------------------------------------------------
    # Publisher UI close detection
    # -----------------------------------------------------------------------

    def _after_publish_ui_close(self):
        logger.debug("Checking if the publisher UI is closed...")
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_publisher_ui_closed)
        self.timer.start(1000)

    def check_publisher_ui_closed(self):
        logger.debug("Checking if the publisher UI is closed through the timer...")
        if os.path.exists(self._publisher_is_closed_path):
            logger.debug("Reading publisher is closed status file {}...".format(self._publisher_is_closed_path))
            with open(self._publisher_is_closed_path, 'r') as infile:
                first_line = infile.readline().strip()

            if "GUI_IS_CLOSED" in first_line:
                self.populate_pending_widget()

            os.remove(self._publisher_is_closed_path)
            self.timer.stop()

    def _wait_for_ui_close(self):
        ui_is_open = True
        while ui_is_open:
            time.sleep(1)
            ui_is_open = self._check_ui_closed()

        msg = "\n <span style='color:#2C93E2'>Updating the Pending View ...</span> \n"
        self._add_log(msg, 2)
        self.update_pending_view()

    def _check_ui_closed(self):
        """Display publisher UI is closed status."""
        try:
            logger.debug(
                "checking for publisher is_closed status file: {} ...".format(self._publisher_is_closed_path))

            if not os.path.exists(self._publisher_is_closed_path):
                logger.debug("publisher is_closed file does not exist")
                return None

            with open(self._publisher_is_closed_path, 'r') as in_file:
                for line in in_file:
                    line = line.rstrip()
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
                            logger.debug("Error: Line does not conform to expected format: '{}'".format(line))
                            return False
                    else:
                        return False
        except Exception as e:
            logger.debug("Error reading publisher is closed file status {}".format(e))
            return False

    # -----------------------------------------------------------------------
    # ShotGrid data
    # -----------------------------------------------------------------------

    def get_current_sg_data(self):
        """
        Populates self._sg_data with ShotGrid publish data from the source model,
        filtering out items marked for deletion.
        """
        total_file_count = 0
        self._sg_data = []
        try:
            model = self._publish_model
            if model.rowCount() > 0:
                items_to_keep = []
                for row in range(model.rowCount()):
                    source_index = model.index(row, 0)
                    item = model.itemFromIndex(source_index)
                    if not item:
                        continue
                    is_folder = item.data(self._SgLatestPublishModel.IS_FOLDER_ROLE)
                    if not is_folder:
                        total_file_count += 1
                        sg_item = item.get_sg_data()
                        if not sg_item:
                            continue
                        action = sg_item.get("action") or sg_item.get("headAction") or None
                        if action and action in ["delete"]:
                            pass
                        else:
                            items_to_keep.append(sg_item)
                self._sg_data = items_to_keep
        except Exception as e:
            logger.error(f"Error in get_current_sg_data: {e}", exc_info=True)
            self._sg_data = []

    def get_current_publish_data(self, entity_id, entity_type):
        self._sg_data = []
        logger.debug("Entity type is {}".format(entity_type))
        if entity_id and entity_type:
            filters = [[]]
            if entity_type == "Asset":
                filters = [["entity.Asset.id", "is", entity_id]]
            elif entity_type == "Shot":
                filters = [["entity.Shot.id", "is", entity_id]]
            elif entity_type == "Task":
                filters = [["task.Task.id", "is", entity_id]]

            entity_published_files = self._app.shotgun.find(
                "PublishedFile",
                filters,
                ["entity", "path_cache", "path", "version_number", "step"],
            )
            self._sg_data = entity_published_files
        else:
            logger.debug("Unable to get current publish data, entity_id or entity_type is None")

    # -----------------------------------------------------------------------
    # Perforce data
    # -----------------------------------------------------------------------

    def _update_perforce_data(self):
        msg = "\n <span style='color:#2C93E2'>Retrieving Data from Perforce...</span> \n"
        self._add_log(msg, 2)
        try:
            self._get_perforce_data()
            msg = "\n <span style='color:#2C93E2'>Perforce Data Retrieval Completed Successfully</span> \n"
        except:
            msg = "\n <span style='color:#2C93E2'>Perforce Data Retrieval Failed</span> \n"
        self._add_log(msg, 2)
        self._publish_model.async_refresh()

    def _update_fstat_data(self):
        """Update the fstat data for the selected entity."""
        selected_item = self._get_selected_entity()
        entity_data = self._load_publishes_for_entity_item_fn(selected_item)
        self._entity_path, entity_id, entity_type = self._get_entity_info(entity_data)
        self.get_current_publish_data(entity_id, entity_type)

        if self._fstat_dict:
            if self._sg_data:
                for sg_item in self._sg_data:
                    sg_item_path = sg_item.get("path", None)
                    if sg_item_path:
                        if "local_path" in sg_item_path:
                            local_path = sg_item_path.get("local_path", None)
                            key = self._create_key(local_path)
                            version_number = sg_item.get("version_number", None)
                            if version_number:
                                version_number = int(version_number)
                                key = "{}#{}".format(key, version_number)
                            else:
                                have_rev = sg_item.get("haveRev", None)
                                if have_rev:
                                    have_rev = int(have_rev)
                                    key = "{}#{}".format(key, have_rev)
                                else:
                                    key = "{}#{}".format(key, 1)
                            if key and key in self._fstat_dict:
                                self._fstat_dict[key]["Published"] = True

    def _fix_fstat_dict(self):
        for key in self._fstat_dict:
            file_path = self._fstat_dict[key].get("clientFile", None)
            if file_path:
                self._fstat_dict[key]["name"] = os.path.basename(file_path)
                self._fstat_dict[key]["path"] = {}
                self._fstat_dict[key]["path"]["local_path"] = file_path

            head_rev = self._fstat_dict[key].get('headRev', "0")
            self._fstat_dict[key]["code"] = "{}#{}".format(self._fstat_dict[key].get("name", None), head_rev)
            p4_status = self._fstat_dict[key].get("headAction", None)
            self._fstat_dict[key]["sg_status_list"] = self._get_p4_status(p4_status)
            self._fstat_dict[key]["depot_file_type"] = self._get_publish_type(file_path)

    def _get_perforce_data(self):
        """Get large Perforce data."""
        self._item_path_dict = defaultdict(int)
        self._fstat_dict = {}
        self._submitted_changes = {}
        self._submitted_data_to_publish = []

        logger.debug("Entity path is: {}".format(self._entity_path))
        try:
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
        except Exception as e:
            pass

        for key in self._item_path_dict:
            if key:
                key = self._convert_local_to_depot(key)
                key = key.rstrip('/')
                max_retries = 3
                fstat_list = None
                try:
                    for attempt in range(max_retries):
                        fstat_list = self._p4.run_fstat('-Of', key + '/...')
                        if not isinstance(fstat_list, list):
                            time.sleep(0.5)
                            continue
                        else:
                            break

                    if not isinstance(fstat_list, list):
                        self._add_log(f"\n Failed to retrieve file status for {key} after {max_retries} retries. \n", 2)
                        fstat_list = []
                except Exception as e:
                    fstat_list = []

                if fstat_list:
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

                                action = fstat.get('action', None) or fstat.get('headAction', None)
                                if action:
                                    sg_status = self._get_p4_status(action)
                                    if sg_status:
                                        self._fstat_dict[newkey]['sg_status_list'] = sg_status
                                change = fstat.get('headChange', None)
                                if change and change in self._submitted_changes:
                                    self._fstat_dict[newkey]['p4_user'] = self._submitted_changes[change]['user']
                                    self._fstat_dict[newkey]['description'] = self._submitted_changes[change]['desc']

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
        """Get a publish type based on extension."""
        publish_type = None
        publish_path = os.path.splitext(publish_path)
        if len(publish_path) >= 2:
            extension = publish_path[1]
            if extension:
                extension = extension.lstrip(".").lower()
                publish_type = self.settings.get(extension, None)
                if not publish_type:
                    publish_type = "%s File" % extension.capitalize()
            else:
                publish_type = "Folder"
        return publish_type

    def _get_p4_status(self, p4_status):
        status = self.status_dict.get(p4_status, None)
        if status:
            return status.lower()
        return None

    def _get_submitted_changelists(self, folder_path):
        try:
            if not self._p4.connected():
                self._p4.connect()
            changes = self._p4.run_changes('-s', 'submitted', f"{folder_path}/...")
            if not isinstance(changes, list):
                logger.error(f"Expected list of changes, got {type(changes)} for path {folder_path}")
                return []
            for change in changes:
                key = change.get('change')
                if key and key not in self._submitted_changes:
                    self._submitted_changes[key] = change
            return changes
        except Exception as e:
            logger.error(f"Failed to retrieve submitted changelists for {folder_path}: {e}")

    # -----------------------------------------------------------------------
    # Perforce UI display helpers
    # -----------------------------------------------------------------------

    def _get_pending_publish_data(self):
        if self._pending_publish_list:
            for publish_item in self._pending_publish_list:
                if publish_item:
                    sg_item = publish_item[0]
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

                    is_published = sg_item.get("Published", None)
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

    def _create_publish_layout(self, data_dict, sorted):
        publish_list = []
        if not sorted:
            node_dictionary = self._get_change_dictionary(data_dict)
        else:
            node_dictionary = data_dict
        for key in node_dictionary.keys():
            if key:
                publish_label = QLabel()
                publish_label.setText(str(key))
                for sg_item in node_dictionary[key]:
                    if sg_item:
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

                        publish_path_line_edit = QLineEdit()
                        publish_path_line_edit.setMinimumWidth(750)
                        publish_path_line_edit.setText('{}'.format(depot_path))

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
        change_txt = ""
        change_list = sg_item.get("change", None)
        if not change_list:
            change_list = sg_item.get("headChange", None)
        if change_list:
            change_txt += "<span style='color:#2C93E2'><B>Change List: </B></span>"
            change_txt += "<span><B>{}   </B></span> ".format(change_list)
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
        publish_time = None
        dt = sg_item.get("headTime", None)
        if dt:
            publish_time = create_publish_timestamp(dt)
        return publish_time

    def _get_publish_user(self, sg_item):
        publish_user, user_name = None, None
        p4_user = sg_item.get("p4_user", None)
        if p4_user:
            publish_user = self._app.shotgun.find_one(
                'HumanUser',
                [['sg_p4_user', 'is', p4_user]],
                ["id", "type", "email", "login", "name", "image"]
            )
        if not publish_user:
            action_owner = sg_item.get("actionOwner", None)
            if action_owner:
                publish_user = self._app.shotgun.find_one(
                    'HumanUser',
                    [['sg_p4_user', 'is', action_owner]],
                    ["id", "type", "email", "login", "name", "image"]
                )
        if not publish_user:
            publish_user = login.get_current_user(self._app.sgtk)
        if publish_user:
            user_name = publish_user.get("name", None)
        return user_name

    def _get_small_perforce_data(self, sg_data):
        """Get small perforce data."""
        if sg_data:
            for i, sg_item in enumerate(sg_data):
                if "path" in sg_item:
                    sg_item_path = sg_item.get("path", None)
                    if sg_item_path:
                        local_path = sg_item_path.get("local_path", None)
                        if local_path:
                            fstat_list = self._p4.run("fstat", local_path)
                            fstat = fstat_list[0]
                            have_rev = fstat.get('haveRev', "0")
                            head_rev = fstat.get('headRev', "0")
                            sg_item["haveRev"], sg_item["headRev"] = have_rev, head_rev
                            sg_item["revision"] = "{}/{}".format(have_rev, head_rev)
        return sg_data

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

    # -----------------------------------------------------------------------
    # Context resolution
    # -----------------------------------------------------------------------

    def _find_task_context(self, path):
        tk = sgtk.sgtk_from_path(path)
        context = tk.context_from_path(path)

        if not context:
            logger.debug(f"{path} does not correspond to any context!")
            return None

        if not context.task:
            if context.entity["type"] == "CustomEntity03":
                if context.step:
                    file_name = os.path.splitext(os.path.basename(path))[0]
                    context_tasks = context.sgtk.shotgun.find(
                        "Task",
                        [["entity", "is", context.entity], ["step", "is", context.step]],
                        ["content"]
                    )
                    for context_task in context_tasks:
                        task_name = context_task.get("content")
                        regex = r"\S*(" + re.escape(task_name) + r"){1}(?:_\w*)?$"
                        matches = re.finditer(regex, file_name)
                        for matchNum, match in enumerate(matches, start=1):
                            for group in match.groups():
                                if group == task_name:
                                    return tk.context_from_entity("Task", context_task["id"])
            elif context.entity["type"] == "Sequence" or context.entity["type"] == "Shot":
                if context.step:
                    return self._find_context(tk, context, path)
            else:
                if not context.step:
                    context_entity = context.sgtk.shotgun.find_one(
                        context.entity["type"],
                        [["id", "is", context.entity["id"]]],
                        ["sg_asset_parent", "sg_asset_type"]
                    )
                    if context_entity.get("sg_asset_type") == "Animations":
                        return self._find_context(tk, context, path)
                elif context.step['name'] == "Animations":
                    return self._find_context(tk, context, path)
                elif context.step['name'] != "Animations":
                    step_tasks = context.sgtk.shotgun.find(
                        "Task",
                        [["entity", "is", context.entity], ["step", "is", context.step]],
                        ['content', 'step', 'sg_status_list']
                    )
                    step_tasks_list = [task for task in step_tasks if task['step'] == context.step]
                    if len(step_tasks_list) == 1:
                        return tk.context_from_entity("Task", step_tasks_list[0]["id"])
                    else:
                        try:
                            inactive_task_states = ['fin', 'omt']  # Reasonable defaults
                            active_tasks = [
                                task for task in step_tasks
                                if task['sg_status_list'] not in inactive_task_states
                            ]
                            if len(active_tasks) == 1:
                                return tk.context_from_entity("Task", active_tasks[0]["id"])
                        except:
                            pass

        return context

    def _find_context(self, tk, context, path):
        file_name = os.path.splitext(os.path.basename(path))[0]
        tasks = context.sgtk.shotgun.find("Task", [["entity", "is", context.entity]], ['content'])
        match_length = len(file_name)
        new_context_id = None

        for task in tasks:
            task_content = task['content']
            new_length = len(file_name) - len(task_content)
            if f"_{task_content}" in file_name and new_length < match_length:
                new_context_id = task['id']
                match_length = new_length

        if new_context_id:
            context = tk.context_from_entity("Task", new_context_id)

        return context

    # -----------------------------------------------------------------------
    # Publish type detection (for files that were not publish type)
    # -----------------------------------------------------------------------

    def _get_published_files(self, sg_item):
        file_path = sg_item['path'].get('local_path', None) if 'path' in sg_item else None
        filters = [
            ["path", "contains", file_path],
            ["entity.Asset.sg_asset_type", "is_not", "Shot"],
        ]
        fields = ["id", "code", "created_at", "user", "action", "step"]
        versions = self._app.shotgun(
            "Version", filters, fields,
            order=[{"field_name": "created_at", "direction": "asc"}]
        )
        logger.debug("versions {}".format(versions))

    def refresh_publish_data(self):
        self._update_perforce_data()
        self._publish_model.hard_refresh()

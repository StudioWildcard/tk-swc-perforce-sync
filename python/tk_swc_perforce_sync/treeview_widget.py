from sgtk.platform.qt import QtCore
for name, cls in QtCore.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

from sgtk.platform.qt import QtGui
for name, cls in QtGui.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls
from collections import OrderedDict
import datetime
from .date_time import create_publish_timestamp
import os
import threading
import sgtk
from sgtk.util import login

from .changelist_selection_operation import ChangelistSelection

logger = sgtk.platform.get_logger(__name__)

#from tank.platform.qt5.QtWidgets import QTreeWidgetItemIterator

class SWCTreeView(QTreeView):
    def __init__(self, parent=None, myp4=None, mode=None):
        super().__init__(parent)

        self.p4 = myp4
        self.parent = parent
        self.mode = mode
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeView.InternalMove)

        #self.setMinimumSize(QSize(1200, 500))

        #self.setMinimumSize(QSize(10000, 600))
        #self.setMaximumSize(QSize(10000, 1500))
        self.setMinimumSize(QSize(10000, 3000))
        self.setMaximumSize(QSize(10000, 5000))
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # self.setProperty("showDropIndicator", False)
        self.setProperty("showDropIndicator", True)
        self.setIconSize(QSize(20, 20))
        self.setStyleSheet("QTreeView::item { padding: 1px; }")
        self.setUniformRowHeights(True)
        self.setSelectionMode(self.selectionMode().ExtendedSelection)
        # self.setSelectionMode(self.selectionMode().MultiSelection)
        # self.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.setHeaderHidden(True)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        # self.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        #self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # self.setDefaultDropAction(Qt.MoveAction)

        # Connect the clicked signal to a custom method
        self.clicked.connect(self.adjust_selection_mode)

        self.setHeaderHidden(True)

        if self.mode:
            self.set_mode(self.mode)
        self.expandAll()

    def clear_selection_except_current(self, current_index):
        """
        Clears all selections in the tree view except for the specified current index.
        """
        model = self.selectionModel()
        for index in model.selectedIndexes():
            if index != current_index:
                model.select(index, QItemSelectionModel.Deselect)

    def adjust_selection_mode(self, index):
        """
        Adjusts the selection mode based on whether the clicked item is a parent or a child.
        """
        is_parent = not index.parent().isValid()
        if self.mode == "submitted":
            if is_parent:
                self.setSelectionMode(QAbstractItemView.SingleSelection)
            else:
                self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        elif self.mode == "pending":
            if is_parent:
                self.setSelectionMode(QAbstractItemView.SingleSelection)
            else:
                # self.setSelectionMode(QAbstractItemView.ExtendedSelection)
                self.setSelectionMode(QAbstractItemView.SingleSelection)


    def adjust_selection_mode_pending(self, index):
        """
        Adjusts the selection mode based on whether the clicked item is a parent or a child.
        """
        is_parent = not index.parent().isValid()

        if is_parent:
            self.setSelectionMode(QAbstractItemView.SingleSelection)
        else:
            self.setSelectionMode(QAbstractItemView.SingleSelection)
            # self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def set_mode(self, mode):
        self.mode = mode
        if self.mode == "submitted":
            # logger.debug("Submitted mode ...")
            self.collapseAll()
        elif self.mode == "pending":
            # logger.debug("Pending mode ...")
            self.expandAll()

    def single_selection(self):
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def multi_selection(self):
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)


    def dropEventOriginal(self, event):
        if event.mimeData().hasUrls():  # Handle external file/folder drops
            logger.debug("External file/folder drop detected.")
            urls = event.mimeData().urls()

            # Determine the target changelist
            target_index = self.indexAt(event.pos())
            target_changelist = target_index.data(QtCore.Qt.UserRole)
            if target_changelist is None:
                target_changelist = "default"  # Use "default" if no specific changelist is targeted
            logger.debug("Target changelist: {}".format(target_changelist))

            # Define a function to process each file
            def process_file(local_path):
                try:
                    fstat_info = self.p4.run_fstat(local_path)
                    logger.debug("fstat_info: {}".format(fstat_info))
                    if fstat_info:
                        fstat_info = fstat_info[0]
                        sg_item = self.create_sg_item_from_fstat(fstat_info)
                        action = fstat_info.get("headAction") or fstat_info.get("action") or None
                        if action:
                            logger.debug("Original action for file: {} is: {}".format(local_path, action))
                            if action == "add":
                                action = "edit"
                                logger.debug("Modified action for file: {} is: {}".format(local_path, action))
                            selected_actions.append((sg_item, action))
                        else:
                            logger.debug("No action found for file: {}".format(local_path))
                    else:
                        logger.debug("No fstat info found for file: {}".format(local_path))
                        sg_item = self.create_sg_item_from_local_path(local_path)
                        action = "edit"
                        selected_actions.append((sg_item, action))
                except Exception as e:
                    logger.error("Error processing file {}: {}".format(local_path, e))

            # Helper function to recursively gather files in a folder
            def gather_files(folder_path):
                import os
                file_paths = []
                for root, _, files in os.walk(folder_path):
                    for file in files:
                        file_paths.append(os.path.join(root, file))
                return file_paths

            # Process each URL in a separate thread
            threads = []
            selected_actions = []

            for url in urls:
                if url.isLocalFile():
                    local_path = url.toLocalFile().replace("\\", "/")
                    if os.path.isdir(local_path):
                        # If it's a folder, gather all files in the folder
                        file_paths = gather_files(local_path)
                        for file_path in file_paths:
                            thread = threading.Thread(target=process_file, args=(file_path,))
                            thread.start()
                            threads.append(thread)
                    else:
                        # If it's a file, process it directly
                        thread = threading.Thread(target=process_file, args=(local_path,))
                        thread.start()
                        threads.append(thread)

            # Wait for all threads to finish
            for thread in threads:
                thread.join()

            logger.debug("Selected actions: {}".format(selected_actions))

            # Add files to the changelist
            try:
                self.perform_changelist_selection(selected_actions)
            except Exception as e:
                logger.error("Error adding files to changelist: {}".format(e))

            event.acceptProposedAction()
        else:
            # Drop event handling for internal items
            if event.source() == self:
                target_index = self.indexAt(event.pos())
                target_changelist = target_index.data(QtCore.Qt.UserRole)
                target_changelist = str(target_changelist)

                for source_index in self.selectedIndexes():
                    source_data = source_index.data(Qt.DisplayRole)
                    source_changelist = source_index.data(QtCore.Qt.UserRole)
                    source_changelist = str(source_changelist)

                    if source_data:
                        dragged_file = source_data.split("#")[0].strip()
                        logger.debug(
                            "Adding dragged file: {} to changelist: {}".format(dragged_file, target_changelist))

                        try:
                            reopen_res = self.p4.run_reopen("-c", target_changelist, dragged_file)
                            logger.debug("Result of reopen: {}".format(reopen_res))
                        except Exception as e:
                            logger.error("Error during reopen: {}".format(e))

                super().dropEvent(event)
            else:
                super().dropEvent(event)

    def dropEvent(self, event):
        """
        Handles drop events, both for internal item moves and external file/folder drops.
        """
        if event.mimeData().hasUrls():  # Handle external file/folder drops
            logger.debug("External file/folder drop detected.")
            urls = event.mimeData().urls()

            # Determine the target changelist (initially, might be refined later)
            target_index = self.indexAt(event.pos())
            # Get the changelist ID from the item dropped onto
            initial_target_changelist = target_index.data(QtCore.Qt.UserRole)
            if initial_target_changelist is None:
                # If dropped onto empty space or an item without a changelist ID (e.g., header)
                # default to 'default'. The ChangelistSelection dialog will handle final selection.
                initial_target_changelist = "default"
            logger.debug("Initial target changelist based on drop location: {}".format(initial_target_changelist))

            # --- File Processing Logic (using threading) ---
            selected_actions = []  # List to hold tuples of (sg_item, action)
            threads = []

            # Define a function to process each file path
            def process_file(local_path):
                try:
                    # Use run_fstat to get Perforce status
                    fstat_info_list = self.p4.run_fstat(local_path)
                    logger.debug(f"fstat info for {local_path}: {fstat_info_list}")

                    sg_item = None
                    action = "add"  # Default action is 'add' for files not in Perforce

                    if fstat_info_list:
                        fstat_info = fstat_info_list[0]  # Assuming one result per file path
                        sg_item = self.create_sg_item_from_fstat(fstat_info)

                        # Determine Perforce action ('edit', 'add', 'delete', etc.)
                        p4_action = fstat_info.get("action") or fstat_info.get("headAction")

                        if p4_action:
                            logger.debug(f"Original Perforce action for file: {local_path} is: {p4_action}")
                            # Map Perforce action to desired publish action if needed
                            if p4_action == "add":
                                action = "edit"  # Treat 'p4 add' as 'edit' for publishing context
                                logger.debug(f"Mapped action for file: {local_path} is: {action}")
                            elif p4_action in ["edit", "integrate", "branch", "move/add"]:
                                action = "edit"
                            elif p4_action in ["delete", "move/delete"]:
                                action = "delete"
                                logger.warning(f"File {local_path} is marked for delete. Handling as 'delete' action.")
                            else:
                                action = p4_action  # Use the action directly if not specifically mapped
                        else:
                            # File exists in Perforce but isn't open for action, treat as 'edit'
                            action = "edit"
                            logger.debug(
                                f"No specific action found for existing file: {local_path}. Defaulting to '{action}'.")

                    else:
                        # File is not in Perforce, create basic sg_item and use 'add' action
                        logger.debug(f"No fstat info found for file: {local_path}. Treating as new file.")
                        sg_item = self.create_sg_item_from_local_path(local_path)
                        action = "add"  # Explicitly 'add' for non-Perforce files

                    # Append the result (sg_item, action) to the shared list (thread-safe append)
                    # Use a lock if modifying shared list directly, or append to thread-local list first
                    # For simplicity here, assuming direct append is okay for this example context
                    if sg_item:
                        # Ensure sg_item has necessary fields for ChangelistSelection/AppDialog
                        sg_item['action'] = action  # Store the determined action
                        selected_actions.append((sg_item, action))

                except Exception as e:
                    logger.error(f"Error processing file {local_path}: {e}")

            # Helper function to recursively gather files in a folder
            def gather_files(folder_path):
                import os
                file_paths = []
                for root, _, files in os.walk(folder_path):
                    for file in files:
                        # Optionally filter files here (e.g., ignore certain extensions)
                        file_paths.append(os.path.join(root, file).replace("\\", "/"))
                return file_paths

            # Process each dropped URL
            for url in urls:
                if url.isLocalFile():
                    local_path = url.toLocalFile().replace("\\", "/")
                    if os.path.isdir(local_path):
                        # If it's a folder, gather all files within it
                        logger.debug(f"Processing dropped folder: {local_path}")
                        file_paths = gather_files(local_path)
                        for file_path in file_paths:
                            thread = threading.Thread(target=process_file, args=(file_path,))
                            threads.append(thread)
                            thread.start()
                    else:
                        # If it's a single file, process it directly
                        logger.debug(f"Processing dropped file: {local_path}")
                        thread = threading.Thread(target=process_file, args=(local_path,))
                        threads.append(thread)
                        thread.start()

            # Wait for all file processing threads to complete
            for thread in threads:
                thread.join()

            logger.debug(f"Finished processing dropped files. Selected actions: {len(selected_actions)}")
            # --- End File Processing Logic ---

            if selected_actions:
                # Show the ChangelistSelection dialog to the user
                # This dialog handles user choice of changelist and performs P4 operations.
                try:
                    # Pass the initially determined target changelist as a suggestion
                    changelist_selector = ChangelistSelection(
                        self.p4,
                        selected_actions=selected_actions,
                        parent=self.parent,  # Pass AppDialog as parent
                        # suggested_changelist=initial_target_changelist
                    )
                    # We assume ChangelistSelection might emit a signal upon success,
                    # or we might modify it to return the result.
                    # Example using a hypothetical signal:
                    # changelist_selector.files_processed.connect(self.parent.handle_files_processed_signal)

                    # For direct return (less ideal):
                    # result_data = changelist_selector.exec_() # or show() if non-modal
                    # if result_data and result_data.get("success"):
                    #    final_changelist_id = result_data.get("changelist_id")
                    #    processed_files_data = result_data.get("processed_files")
                    #    # Now update the parent's model
                    #    if self.parent and hasattr(self.parent, 'add_dropped_files_to_changelist'):
                    #        logger.info(f"Updating parent model for changelist {final_changelist_id}")
                    #        self.parent.add_dropped_files_to_changelist(final_changelist_id, processed_files_data)
                    #    else:
                    #        logger.warning("Parent or add_dropped_files_to_changelist method not found.")

                    # Showing the dialog (assuming it handles the rest, including signaling parent)
                    changelist_selector.show()

                except Exception as e:
                    logger.error(f"Error during changelist selection/processing: {e}")
            else:
                logger.warning("No valid actions determined for dropped files.")

            event.acceptProposedAction()

        # --- Internal Move Logic ---
        elif event.source() == self:
            # Handle internal drag and drop (moving items between changelists in the view)
            target_index = self.indexAt(event.pos())
            if not target_index.isValid():
                logger.warning("Internal drop target index is invalid.")
                event.ignore()
                return

            # Ensure the drop target is a changelist item (parent node)
            if target_index.parent().isValid():  # Dropped onto a file, not a changelist
                # Try getting the parent index
                target_index = target_index.parent()
                if not target_index.isValid():
                    logger.warning("Cannot drop file onto another file. Drop onto a changelist.")
                    event.ignore()
                    return

            target_changelist_id = target_index.data(QtCore.Qt.UserRole)
            if target_changelist_id is None:
                logger.warning("Internal drop target is not a valid changelist.")
                event.ignore()
                return

            target_changelist_id = str(target_changelist_id)
            logger.debug(f"Internal move target changelist: {target_changelist_id}")

            moved_files_info = []  # To potentially update model later if needed

            # Process each selected file being dragged
            selected_indexes = self.selectedIndexes()
            source_files = []
            for source_index in selected_indexes:
                # Ensure we only process file items (children), not changelist items (parents)
                if source_index.parent().isValid():
                    source_data = source_index.data(Qt.DisplayRole)  # e.g., //depot/file#rev
                    source_changelist_id = str(source_index.data(QtCore.Qt.UserRole))  # CL of the source item

                    if source_data:
                        # Extract depot path (remove revision info if present)
                        dragged_file_depot_path = source_data.split("#")[0].strip()
                        source_files.append(dragged_file_depot_path)
                        logger.debug(
                            f"Preparing to move file: {dragged_file_depot_path} from CL {source_changelist_id} to CL {target_changelist_id}")

            if source_files:
                # Perform the Perforce 'reopen' command for all files at once
                try:
                    # Ensure target changelist exists (p4 change -o needs existing CL or 'default')
                    # Note: 'default' might need special handling if files are added first.
                    # 'p4 reopen' moves open files between changelists.
                    reopen_args = ["-c", target_changelist_id] + source_files
                    reopen_res = self.p4.run_reopen(*reopen_args)
                    logger.debug(f"Perforce reopen result: {reopen_res}")

                    # Check result for errors (p4python usually raises exceptions on error)
                    # If successful, proceed with the default Qt drop event to update the view
                    super().dropEvent(event)  # Updates the TreeView UI

                    # OPTIONAL: If you need to update the AppDialog's internal _change_dict
                    # after the move, you would need logic here or in ChangelistSelection
                    # to signal the parent with the moved files and target CL.
                    # For example:
                    # if self.parent and hasattr(self.parent, 'handle_files_moved_signal'):
                    #    self.parent.handle_files_moved_signal(target_changelist_id, source_files)

                except Exception as e:
                    logger.error(f"Error during Perforce reopen operation: {e}")
                    # Don't accept the drop if p4 command failed
                    event.ignore()
            else:
                logger.warning("No valid source files identified for internal move.")
                event.ignore()

        else:
            # Handle drops from other sources if necessary, otherwise ignore or call super
            logger.debug("Drop event from unrecognized source.")
            super().dropEvent(event)  # Or event.ignore() if only internal/URL drops are allowed

    def dragEnterEvent(self, event):
        if event.source() == self:
            event.setDropAction(Qt.MoveAction)
            event.accept()
        elif event.mimeData().hasUrls():  # Check for external file drops
            logger.debug("Drag event with URLs detected.")
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def getSelectedIndexes(self):
        return self.selectionModel().selectedIndexes()

    def getSizeHint(self):
        return self.sizeHint()

    def setFirstColumn(self, i):
        return self.setFirstColumnSpanned(i, self.rootIndex(), True)


    def create_sg_item_from_fstat(self, fstat_info):
        """
        Create sg_item from fstat info, ensuring lowercase extension and forward slashes for local_path.
        """
        sg_item = fstat_info.copy()  # Create a copy to avoid modifying the original dict
        client_file = fstat_info.get("clientFile", None)
        if client_file:
            # Normalize path separators to forward slashes
            normalized_path = client_file.replace("\\", "/")  # ADDED

            # Ensure the local path uses a lowercase extension
            root, ext = os.path.splitext(normalized_path)
            normalized_path_lower_ext = root + ext.lower()  # MODIFIED

            sg_item["path"] = {}
            sg_item["path"]["local_path"] = normalized_path_lower_ext  # MODIFIED
            # Keep original clientFile if needed elsewhere, or remove if only normalized is used
            # sg_item["original_clientFile"] = client_file
        return sg_item

    def create_sg_item_from_local_path(self, local_path):
        """
        Create sg_item from local path, ensuring lowercase extension and forward slashes.
        """
        sg_item = {}
        # Normalize path separators to forward slashes
        normalized_path = local_path.replace("\\", "/")  # ADDED

        # Ensure the local path uses a lowercase extension
        root, ext = os.path.splitext(normalized_path)
        normalized_path_lower_ext = root + ext.lower()  # MODIFIED

        sg_item["path"] = {}
        sg_item["path"]["local_path"] = normalized_path_lower_ext  # MODIFIED
        # Depot path generation might also need review depending on P4/SG setup,
        # but let's focus on the local_path used for SG lookups first.
        # Use the fully normalized path when generating depot path too
        sg_item["depotFile"] = self.get_depot_filepath(normalized_path_lower_ext)  # MODIFIED

        return sg_item



    def get_depot_filepath(self, local_path):

        # Convert local path to depot path
        # For example, convert: 'B:\\Ark2Depot\\Content\\Base\\Characters\\Human\\Survivor\\Armor\\Cloth_T3\\_ven\\MDL\\Survivor_M_Armor_Cloth_T3_MDL.fbx'
        # to "//Ark2Depot/Content/Base/Characters/Human/Survivor/Armor/Cloth_T3/_ven/MDL/Survivor_M_Armor_Cloth_T3_MDL.fbx"

        local_path = local_path[2:]
        depot_path = local_path.replace("\\", "/")
        depot_path = "/{}".format(depot_path)
        return depot_path

    def perform_changelist_selection(self, selected_actions):
        perform_action = ChangelistSelection(self.p4, selected_actions=selected_actions, parent=self.parent)
        perform_action.show()

class ChangeItem( QStandardItem):
    def __init__(self, parent=None, key=None, data=None, icon=None, enabled=None):
        super().__init__(parent)
        self.key = key

        self.setFlags(
            (self.flags() | Qt.ItemFlag.ItemIsDropEnabled) & ~Qt.ItemFlag.ItemIsDragEnabled
        )

        msg = "Changelist# {}".format(self.key)
        self.setToolTip(msg)
        self.setData(key, QtCore.Qt.UserRole)
        self.setSizeHint(QSize(0, 25))
        self.setEditable(False)
        self.setText(data)
        self.setIcon(icon)
        #self.setDropEnabled(enabled)
        self.setEnabled(enabled)

class DepotItem( QStandardItem):
    def __init__(self, parent=None, key=None, data=None, icon=None, enabled=False, size_hint=25):
        super().__init__(parent)


        self.setIcon(icon)
        self.setFlags(
            (
                self.flags() | Qt.ItemFlag.ItemIsDragEnabled) & ~Qt.ItemFlag.ItemIsDropEnabled
        )
        #self.setData(key, QtCore.Qt.UserRole)
        self.setSizeHint(QSize(0, 25))
        self.setTextAlignment(
            Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)
        self.setText(data)
        self.setEnabled(enabled)

class TreeViewWidget(QWidget):
    """
    TreeView Widget
    """
    selected_item_signal = QtCore.Signal(QModelIndex)
    def __init__(self, data_dict=None, sorted=False, mode=None, p4=None, parent=None):
        super(TreeViewWidget, self).__init__()
        self.data_dict = {}
        self.sorted = sorted
        self.mode = mode
        self.p4 = p4
        self.parent = parent

        self._app = sgtk.platform.current_bundle()

        # set up layout
        self.main_layout = QVBoxLayout()

        # major widgets

        self.tree_view = SWCTreeView(myp4=self.p4, parent=self.parent, mode=self.mode)
        self.tree_view.set_mode(self.mode)
        self.model = QStandardItemModel()
        self.proxymodel = QtGui.QSortFilterProxyModel()
        self.proxymodel.setSourceModel(self.model)
        self.tree_view.setModel(self.proxymodel)

        self.publish_dict = {}

        # Data
        if data_dict:
            self.data_dict = data_dict

        # Icons
        self.repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        submitted_image_path = os.path.join(self.repo_root, "icons/mode_switch_submitted_active.png")
        self.submitted_icon = QIcon(QPixmap(submitted_image_path))

        pending_image_path = os.path.join(self.repo_root, "icons/mode_switch_pending_active.png")
        self.pending_icon = QIcon(QPixmap(pending_image_path))

        p4_file_add_path = os.path.join(self.repo_root, "icons/p4_file_add.png")
        self.p4_file_add_icon = QIcon(QPixmap(p4_file_add_path))

        p4_file_edit_path = os.path.join(self.repo_root, "icons/p4_file_edit.png")
        self.p4_file_edit_icon = QIcon(QPixmap(p4_file_edit_path))

        p4_file_delete_path = os.path.join(self.repo_root, "icons/p4_file_delete.png")
        self.p4_file_delete_icon = QIcon(QPixmap(p4_file_delete_path))

    def set_mode(self):
        self.tree_view.set_mode(self.mode)

        #self.pending_icon = QIcon(":/res/pending.png")
    def single_selection(self):
        self.tree_view.single_selection()

    def multi_selection(self):
        self.tree_view.multi_selection()

    def select_items(self):
        #selected = self.tree_view.getSelectedIndexes()
        selected = self.tree_view.selectionModel().selectedIndexes()
        for index in selected:
            item = self.model.data(index)
            if item:
                for row in item.childCount():
                    child_item = item.child(row)
                    child_item.setSelected(True)

    def get_selected_publish_items(self):
        data_to_publish = []
        selected = self.tree_view.selectionModel().selectedIndexes()
        for index in selected:
            key = self.model.data(index)
            if key:
                if key in self.publish_dict:
                    sg_item = self.publish_dict.get(key, None)
                    if sg_item:
                        data_to_publish.append(sg_item)

        #logger.debug("<<<<<<<  self.publish_dict: {}".format(self.publish_dict))
        #logger.debug("<<<<<<<  data_to_publish: {}".format(data_to_publish))
        return data_to_publish

    def get_selected_publish_items_by_action(self):
        delete_data_to_publish = {}
        other_data_to_publish = {}
        selected = self.tree_view.selectionModel().selectedIndexes()
        for index in selected:
            depot_key = self.model.data(index)
            logger.debug("get_selected_publish_items_by_action: <<<<<<<  depot_key: {}".format(depot_key))
            if depot_key:
                if depot_key in self.publish_dict:
                    sg_item = self.publish_dict.get(depot_key, None)
                    logger.debug("get_selected_publish_items_by_action: <<<<<<<  sg_item: {}".format(sg_item))
                    if sg_item:
                        key = sg_item.get("key", None)
                        if key:

                            action = self._get_action(sg_item)
                            if action not in ["delete"]:
                                if key not in other_data_to_publish:
                                    other_data_to_publish[key] = []
                                other_data_to_publish[key].append(sg_item)

                            else:
                                if key not in delete_data_to_publish:
                                    delete_data_to_publish[key] = []
                                delete_data_to_publish[key].append(sg_item)

        #logger.debug("<<<<<<<  self.publish_dict: {}".format(self.publish_dict))
        #logger.debug("<<<<<<<  data_to_publish: {}".format(data_to_publish))
        return other_data_to_publish, delete_data_to_publish

    def _get_action(self, sg_item):
        """
        Get action
        """
        action = sg_item.get("action", None)
        if not action:
            action = sg_item.get("headAction", None)
        return action


    def get_all_publish_items(self):
        data_to_publish = []
        #selected = self.tree_view.getSelectedIndexes()
        selected = self.tree_view.selectionModel().selectedIndexes()
        for index in selected:
            key = self.model.data(index)
            if key:
                if key in self.publish_dict:
                    sg_item = self.publish_dict.get(key, None)
                    if sg_item:
                        data_to_publish.append(sg_item)

        #logger.debug("<<<<<<<  self.publish_dict: {}".format(self.publish_dict))
        #logger.debug("<<<<<<<  data_to_publish: {}".format(data_to_publish))
        return data_to_publish


    def get_treeview_widget(self):
        #return self.main_layout
        self.tree_view.set_mode(self.mode)
        return self.tree_view

    def get_published_status(self, change_list):
        for sg_item in change_list:
            if sg_item:
                is_published = sg_item.get("Published", None)
                if not is_published:
                    return True
        return False

    def populate_treeview_widget_submitted(self):
        """
        Populate treeview widget with data from data_dict
        """

        parent_icon = self.submitted_icon
        node_dictionary = self._get_change_dictionary_submitted(self.data_dict)
        item_data = None

        for i, key in enumerate(node_dictionary.keys()):
            if key:
                #logger.debug("<<<<<<<  key: {}".format(key))
                self.tree_view.setFirstColumnSpanned(i, self.tree_view.rootIndex(), True)
                is_change_not_published = False
                change_list = node_dictionary[key]
                if change_list and len(change_list) > 0:
                    is_change_not_published = self.get_published_status(change_list)

                    sg_item = change_list[0]
                    if sg_item:
                        publish_time_txt = self._get_publish_time_info(sg_item)
                        user_name_txt = sg_item.get("p4_user", None)
                        description_txt = sg_item.get("description", None)

                        item_data = "{} \t {} \t {} \t {}".format(key, publish_time_txt, user_name_txt, description_txt)
                change_item = ChangeItem(key=str(key),
                                                 data=item_data,
                                                 icon=parent_icon,
                                                 enabled=is_change_not_published)
                self.model.appendRow([change_item])

                for sg_item in change_list:
                    if sg_item:
                        depot_item = self.create_depot_item(key, sg_item)
                        if depot_item:
                            change_item.appendRow(depot_item)



    def create_depot_item(self, key, sg_item):
        """ Create depot item """
        enable_change_item = False
        depot_path = sg_item.get("depotFile", None)
        head_rev = sg_item.get("headRev", "0")

        is_published = sg_item.get("Published", None)
        if not is_published:
            enable_change_item = True
        action = self._get_action(sg_item)
        action_icon = self.get_action_icon(action)
        if depot_path:
            depot_str = depot_path
            if head_rev != "0":
                revision = sg_item.get("revision", None)
                if revision:
                    depot_str = "{}{}".format(depot_path, revision)
                else:
                    depot_str = "{}#{}".format(depot_path, head_rev)
            #logger.debug("<<<<<<<  depot_str: {}".format(depot_str))
            size_hint = self.tree_view.sizeHint()
            depot_item = DepotItem(key=key, data=depot_str, icon=action_icon, enabled=enable_change_item, size_hint=size_hint)
            return depot_item
        return None

    def populate_treeview_widget_submitted_old(self):
        """
        Populate treeview widget with data from data_dict
        """
        self.publish_dict = {}
        parent_icon = self.submitted_icon
        node_dictionary = self._get_change_dictionary_submitted(self.data_dict)

        for i, key in enumerate(node_dictionary.keys()):
            if key:
                logger.debug("<<<<<<<  key: {}".format(key))
                key_str = str(key)
                change_item = QStandardItem(key_str)
                # change_item must allow drops, but cannot be dragged
                change_item.setFlags(
                    (change_item.flags() | Qt.ItemFlag.ItemIsDropEnabled) & ~Qt.ItemFlag.ItemIsDragEnabled
                )

                msg = "Changelist# {}".format(key)
                change_item.setToolTip(msg)
                change_item.setData(key, QtCore.Qt.UserRole)
                change_item.setSizeHint(QSize(0, 25))
                change_item.setEditable(False)
                self.model.appendRow([change_item])

                self.tree_view.setFirstColumnSpanned(i, self.tree_view.rootIndex(), True)
                enable_change_item = False
                if node_dictionary[key]:

                    for j, sg_item in enumerate(node_dictionary[key]):
                        logger.debug("<<<<<<<  setting file ...")
                        if 'changeListInfo' in sg_item:
                            publish_time_txt = self._get_publish_time_info(sg_item)
                            user_name_txt = self._get_user_name_info(sg_item)
                            description_txt = self._get_description_info(sg_item)

                            msg = "{} \t {} \t {} \t {}".format(key, publish_time_txt, user_name_txt, description_txt)
                            change_item.setText(msg)
                        else:

                            depot_path = sg_item.get("depotFile", None)
                            head_rev = sg_item.get("headRev", "0")
                            revision = sg_item.get("revision", None)
                            is_published = sg_item.get("Published", None)
                            if not is_published:
                                enable_change_item = True
                            action = self._get_action(sg_item)
                            action_icon = self.get_action_icon(action)
                            if depot_path:
                                depot_str = depot_path
                                if head_rev != "0":
                                    if revision:
                                        depot_str = "{}{}".format(depot_path, revision)
                                    else:
                                        depot_str = "{}#{}".format(depot_path, head_rev)
                                depot_item = QStandardItem(depot_str)
                                # depot_item can be dragged, but must not accept drops
                                depot_item.setFlags(
                                    (
                                                depot_item.flags() | Qt.ItemFlag.ItemIsDragEnabled) & ~Qt.ItemFlag.ItemIsDropEnabled
                                )
                                depot_item.setIcon(action_icon)
                                depot_item.setData(key, QtCore.Qt.UserRole)

                                depot_item.setSizeHint(self.tree_view.sizeHint())

                                depot_item.setTextAlignment(
                                    Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)
                                change_item.appendRow(depot_item)

                                if is_published:
                                    depot_item.setEnabled(False)
                                else:
                                    if depot_str not in self.publish_dict:
                                        self.publish_dict[depot_str] = sg_item
                            """
                            if j == 0:
                                publish_time_txt = self._get_publish_time_info(sg_item)
                                user_name_txt = self._get_user_name_info(sg_item)
                                description_txt = self._get_description_info(sg_item)

                                msg = "{} \t {} \t {} \t {}".format(key, publish_time_txt, user_name_txt, description_txt)
                                change_item.setText(msg)
                            """

                if parent_icon is not None:
                    change_item.setIcon(parent_icon)

                if enable_change_item:
                    change_item.setEnabled(True)
                else:
                    change_item.setEnabled(False)

    def populate_treeview_widget_pending(self):
        """
        Populate treeview widget with data from data_dict
        """
        #logger.debug("<<<<<<<  populate_treeview_widget ...")
        self.publish_dict = {}
        parent_icon = self.pending_icon

        node_dictionary = self._get_change_dictionary_pending(self.data_dict)


        for i, key in enumerate(node_dictionary.keys()):
            if key:
                #logger.debug("<<<<<<<  key: {}".format(key))
                key_str = str(key)
                change_item = QStandardItem(key_str)
                # change_item must allow drops, but cannot be dragged
                change_item.setFlags(
                    (change_item.flags() | Qt.ItemFlag.ItemIsDropEnabled) & ~Qt.ItemFlag.ItemIsDragEnabled
                )

                msg = "Right-click the selected changelist '{}' and choose 'Publish...' to publish it in Shotgrid.".format(
                    key)
                change_item.setToolTip(msg)
                change_item.setData(key, QtCore.Qt.UserRole)
                change_item.setData(key, QtCore.Qt.UserRole + 2)

                change_item.setSizeHint(QSize(0, 25))
                change_item.setEditable(False)
                self.model.appendRow([change_item])

                self.tree_view.setFirstColumnSpanned(i, self.tree_view.rootIndex(), True)

                if node_dictionary[key]:

                    for j, sg_item in enumerate(node_dictionary[key]):
                        #logger.debug("<<<<<<<  setting file ...")
                        description_txt = ""
                        logger.debug("<<<<<<<populate_treeview_widget_pending  sg_item: {}".format(sg_item))
                        if 'changeListInfo' in sg_item:
                            publish_time_txt = self._get_publish_time_info(sg_item)
                            user_name_txt = sg_item.get("p4_user", None)
                            description_txt = sg_item.get("description", None)

                            msg = "{} \t {} \t {} \t {}".format(key, publish_time_txt, user_name_txt, description_txt)
                            change_item.setText(msg)
                            change_item.setData(description_txt, QtCore.Qt.UserRole + 4)
                        else:

                            depot_path = sg_item.get("depotFile", None)
                            head_rev = sg_item.get("headRev", "0")
                            revision = sg_item.get("revision",  None)

                            action = self._get_action(sg_item)
                            action_icon = self.get_action_icon(action)
                            if depot_path:
                                depot_str = depot_path
                                if head_rev != "0":
                                    if revision:
                                        depot_str = "{} {}".format(depot_path, revision)
                                    else:
                                        depot_str = "{}#{}".format(depot_path, head_rev)
                                depot_item = QStandardItem(depot_str)
                                # depot_item can be dragged, but must not accept drops
                                depot_item.setFlags(
                                    (depot_item.flags() | Qt.ItemFlag.ItemIsDragEnabled) & ~Qt.ItemFlag.ItemIsDropEnabled
                                )
                                # msg = "Right-click the selected file 'Revert' the file in Perforce. "
                                msg = "Select the file for further action"
                                depot_item.setToolTip(msg)

                                depot_item.setIcon(action_icon)
                                depot_item.setData(key, QtCore.Qt.UserRole)
                                depot_item.setTextAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)
                                depot_item.setData(action, QtCore.Qt.UserRole + 1)
                                depot_item.setData(key, QtCore.Qt.UserRole + 2)
                                depot_item.setData(sg_item, QtCore.Qt.UserRole + 3)
                                depot_item.setData(description_txt, QtCore.Qt.UserRole + 4)
                                change_item.appendRow(depot_item)


                                if depot_str not in self.publish_dict:
                                    self.publish_dict[depot_str] = sg_item


                if parent_icon is not None:
                    change_item.setIcon(parent_icon)

                change_item.setEnabled(True)


    def _create_perforce_ui(self, data_dict, sorted=None):
        # publish list
        publish_widget = QWidget()
        publish_layout = QVBoxLayout()

        # Create a proxy model.
        proxy_model = QtGui.QSortFilterProxyModel(self)
        proxy_model.setSourceModel(model)

        # Impose and keep the sorting order on the default display role text.
        proxy_model.sort(0)
        proxy_model.setDynamicSortFilter(True)

        # Create a Tree View
        view = QTreeView(tab)
        publish_layout.addWidget(view)

        # Configure the view.
        view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        view.setProperty("showDropIndicator", False)
        view.setIconSize(QSize(20, 20))
        view.setStyleSheet("QTreeView::item { padding: 6px; }")
        view.setUniformRowHeights(True)
        view.setHeaderHidden(True)
        view.setModel(proxy_model)

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
                    user_name_label.setMaximumWidth(2000)
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

    def _create_publish_layout(self, data_dict, sorted):
        publish_list = []
        if not sorted:
            node_dictionary = self._get_change_dictionary_submitted(data_dict)
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
                        #action_icon = self.get_action_icon(action)

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

    def get_action_icon(self, action):
        action_icon = self.p4_file_add_icon
        if action:
            if action == "edit":
                action_icon  = self.p4_file_edit_icon
            elif action == "delete":
                action_icon = self.p4_file_delete_icon
            else:
                action_icon = self.p4_file_add_icon
        return action_icon


    def _get_change_dictionary_submitted(self, data_dict):
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

    def _get_change_dictionary_pending(self, data_dict):
        """
        Creates dictionary for every changelist and all its depot files
        key: changelist number
        value: sorted list of depotfiles
        :return: dictionary
        """

        change_dict_sorted = OrderedDict(sorted(data_dict.items()))

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
        if not publish_time:
            return ""
        #if publish_time:
        #    publish_time_txt += "<span style='color:#2C93E2'><B>Creation Time: </B></span>"
        #    publish_time_txt += "<span><B>{}   </B></span>".format(publish_time)

        return publish_time

    def _get_user_name_info(self, sg_item):
        user_name_txt = ""

        user_name = self._get_publish_user(sg_item)
        #if user_name:
        #    user_name_txt += "<span style='color:#2C93E2'><B>User: </B></span>"
        #    user_name_txt += "<span><B>{}   </B></span>\t\t".format(user_name)
        return user_name

    def _get_description_info(self, sg_item):
        description_txt = ""

        description = sg_item.get("description", None)
        #if description:
        #    description_txt += "<span style='color:#2C93E2'><B>Description: </B></span>"
        #    description_txt += "<span><B>{}</B></span>\t\t".format(description)

        return description

    def _get_publish_time(self, sg_item):
        publish_time = None
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

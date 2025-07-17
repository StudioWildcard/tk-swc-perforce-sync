import os
import datetime
import threading

# Modern, direct Qt imports
from sgtk.platform.qt import QtCore, QtGui
from tank_vendor import shotgun_api3
import sgtk

# Set up logger
logger = sgtk.platform.get_logger(__name__)


class SubmitChangelistWidget(QtGui.QDialog):
    """
    A dialog for editing and submitting a Perforce changelist. It allows users
    to review files, change their ShotGrid context, and submit them.
    """

    def __init__(self, parent=None, myp4=None, change_item=None, file_dict=None):
        super(SubmitChangelistWidget, self).__init__(parent)

        # --- Member Variables ---
        self.parent = parent
        self.p4 = myp4
        self.change_sg_item = change_item
        self.submit_widget_dict = file_dict or {}
        self.context_cache = {}

        # --- UI Setup ---
        self._setup_ui()

        # --- Initial Population ---
        self.update_buttons_state()
        self.populate_file_table()

    def _setup_ui(self):
        """Initializes and lays out all UI widgets."""
        self.setObjectName('submit_changelist_widget')
        self.setMinimumSize(1400, 865)
        self.setWindowTitle('Submit Changelist')

        # --- Layouts ---
        self.main_layout = QtGui.QVBoxLayout(self)
        self.top_layout = QtGui.QGridLayout()
        self.button_layout = QtGui.QHBoxLayout()

        # --- Top Info Section ---
        self._setup_info_widgets()

        # --- Description ---
        self.changelist_desc_label = QtGui.QLabel('Description:')
        self.changelist_description = QtGui.QTextEdit()
        self.changelist_description.setPlaceholderText("Enter changelist description here...")
        self.changelist_description.setFixedHeight(100)
        self.changelist_description.textChanged.connect(self.update_buttons_state)

        # --- Files Table ---
        self.files_label = QtGui.QLabel('Files to Submit:')
        self._setup_files_table()

        # --- Buttons ---
        self._setup_buttons()

        # --- Assemble Main Layout ---
        self.main_layout.addLayout(self.top_layout)
        self.main_layout.addWidget(QtGui.QLabel(''))  # Spacer
        self.main_layout.addWidget(self.changelist_desc_label)
        self.main_layout.addWidget(self.changelist_description)
        self.main_layout.addWidget(self.files_label)
        self.main_layout.addWidget(self.files_table_widget)
        self.main_layout.addLayout(self.button_layout)

    def _setup_info_widgets(self):
        """Sets up the static info labels at the top of the dialog."""
        self.changelist_label = QtGui.QLabel('Changelist:')
        self.changelist_value = QtGui.QLabel('')
        self.date_label = QtGui.QLabel('Date:')
        self.date_value = QtGui.QLabel('')
        self.workspace_label = QtGui.QLabel('Workspace:')
        self.workspace_value = QtGui.QLabel('')
        self.user_label = QtGui.QLabel('User:')
        self.user_value = QtGui.QLabel('')

        self.top_layout.addWidget(self.changelist_label, 0, 0, QtCore.Qt.AlignRight)
        self.top_layout.addWidget(self.changelist_value, 0, 1, QtCore.Qt.AlignLeft)
        self.top_layout.addWidget(self.date_label, 1, 0, QtCore.Qt.AlignRight)
        self.top_layout.addWidget(self.date_value, 1, 1, QtCore.Qt.AlignLeft)
        self.top_layout.addWidget(self.workspace_label, 0, 2, QtCore.Qt.AlignRight)
        self.top_layout.addWidget(self.workspace_value, 0, 3, QtCore.Qt.AlignLeft)
        self.top_layout.addWidget(self.user_label, 1, 2, QtCore.Qt.AlignRight)
        self.top_layout.addWidget(self.user_value, 1, 3, QtCore.Qt.AlignLeft)

        self.top_layout.setColumnStretch(1, 1)
        self.top_layout.setColumnStretch(3, 1)

    def _setup_files_table(self):
        """Sets up the main table for displaying files."""
        self.files_table_widget = QtGui.QTableWidget(0, 11)
        self.files_table_widget.setHorizontalHeaderLabels([
            '', 'File', 'In Folder', 'Resolve Status', 'Type', 'Pending Action',
            'Changelist', 'Entity Name', 'Entity ID', 'Context', 'Comment'
        ])

        # Enable sorting by clicking headers
        self.files_table_widget.setSortingEnabled(True)

        # Allow columns to be interactively resized by the user
        header = self.files_table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QtGui.QHeaderView.ResizeToContents)
        for col_idx in range(1, 10):
            header.setSectionResizeMode(col_idx, QtGui.QHeaderView.Interactive)
        header.setSectionResizeMode(10, QtGui.QHeaderView.Stretch)

        # Set sensible initial widths for path columns
        self.files_table_widget.setColumnWidth(1, 250)
        self.files_table_widget.setColumnWidth(2, 300)
        self.files_table_widget.setColumnWidth(9, 200)

        # Enable the right-click context menu
        self.files_table_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.files_table_widget.customContextMenuRequested.connect(self._show_files_table_context_menu)

    def _setup_buttons(self):
        """Sets up the buttons at the bottom of the dialog."""
        self.select_all_button = QtGui.QPushButton('Select All')
        self.select_none_button = QtGui.QPushButton('Select None')
        self.submit_button = QtGui.QPushButton('Submit')
        self.save_button = QtGui.QPushButton('Save')
        self.cancel_button = QtGui.QPushButton('Cancel')

        self.submit_button.setToolTip('Submit the selected files in the changelist')
        self.save_button.setToolTip('Save the changelist description')
        self.cancel_button.setToolTip('Cancel the operation')

        self.select_all_button.clicked.connect(self.select_all)
        self.select_none_button.clicked.connect(self.select_none)
        self.submit_button.clicked.connect(self.submit_changelist)
        self.save_button.clicked.connect(self.save_changelist)
        self.cancel_button.clicked.connect(self.cancel_action)

        self.button_layout.addWidget(self.select_all_button)
        self.button_layout.addWidget(self.select_none_button)
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.submit_button)
        self.button_layout.addWidget(self.save_button)
        self.button_layout.addWidget(self.cancel_button)

    # --- Table Population and Data Handling ---

    def populate_file_table(self):
        """
        Populates the file table with data from the submission dictionary.
        This method handles entity processing, sorting, and UI updates.
        """
        # --- 1. Set dialog header info ---
        self.changelist_value.setText(str(self.change_sg_item.get("change", "")))
        self.date_value.setText(self._fix_timestamp(self.change_sg_item.get("headTime", "")))
        self.workspace_value.setText(self.change_sg_item.get("client", ""))
        self.user_value.setText(self.change_sg_item.get("p4_user", ""))
        self.changelist_description.setText(self.change_sg_item.get("description", ""))

        # --- 2. Process entities in a background thread ---
        if self.submit_widget_dict:
            entity_thread = threading.Thread(
                target=self.process_entities,
                args=(self.submit_widget_dict, self.get_entity)
            )
            entity_thread.start()
            entity_thread.join()  # Wait for processing to finish

        # --- 3. Prepare and populate table ---
        self.files_table_widget.setSortingEnabled(False)  # Disable for performance
        self.files_table_widget.setRowCount(0)

        # Sort items to visually group them by source changelist
        sorted_items = sorted(self.submit_widget_dict.items(), key=self._sort_key_func)

        for key, file_info in sorted_items:
            self._add_row_to_table(self.files_table_widget.rowCount(), key, file_info)

        self.files_table_widget.setSortingEnabled(True)
        self.update_buttons_state()

    def _add_row_to_table(self, row, key, file_info):
        """Adds a single row of data to the files table."""
        self.files_table_widget.insertRow(row)

        sg_item = file_info.get("sg_item", {})
        entity = sg_item.get("entity")

        # Column 0: Checkbox
        checkbox_item = QtGui.QTableWidgetItem()
        checkbox_item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
        checkbox_item.setCheckState(QtCore.Qt.Checked)
        self.files_table_widget.setItem(row, 0, checkbox_item)

        # Column 1: File (store unique key in UserRole)
        file_item = self._create_item_with_tooltip(file_info.get("file", "N/A"))
        file_item.setData(QtCore.Qt.UserRole, key)
        self.files_table_widget.setItem(row, 1, file_item)

        # Populate other data columns
        self.files_table_widget.setItem(row, 2, self._create_item_with_tooltip(file_info.get("folder")))
        self.files_table_widget.setItem(row, 3, self._create_item_with_tooltip(file_info.get("resolve_status")))
        self.files_table_widget.setItem(row, 4, self._create_item_with_tooltip(file_info.get("type")))
        self.files_table_widget.setItem(row, 5, self._create_item_with_tooltip(file_info.get("pending_action")))
        source_cl = sg_item.get("headChange") or sg_item.get("change", "N/A")
        self.files_table_widget.setItem(row, 6, self._create_item_with_tooltip(source_cl))

        # Populate entity info
        is_entity_recognized = isinstance(entity, dict)
        entity_name = entity.get("name", "None") if is_entity_recognized else "None"
        entity_id = entity.get("id", "None") if is_entity_recognized else "None"
        context_str = sg_item.get("context", "None")
        comment = "Entity is recognizable" if is_entity_recognized else "Entity is not recognized"

        self.files_table_widget.setItem(row, 7, self._create_item_with_tooltip(entity_name))
        self.files_table_widget.setItem(row, 8, self._create_item_with_tooltip(str(entity_id)))
        self.files_table_widget.setItem(row, 9, self._create_item_with_tooltip(context_str))
        self.files_table_widget.setItem(row, 10, self._create_item_with_tooltip(comment))

        # Style row if entity is not recognized
        if not is_entity_recognized:
            for col_idx in range(self.files_table_widget.columnCount()):
                item = self.files_table_widget.item(row, col_idx)
                item.setForeground(QtGui.QBrush(QtCore.Qt.red))
                if col_idx > 0:
                    item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)

    def process_entities(self, submit_widget_dict, get_entity_callback):
        """Worker method to process entities in a background thread."""
        for key, file_info in submit_widget_dict.items():
            if "sg_item" in file_info:
                file_info["sg_item"] = get_entity_callback(file_info["sg_item"])

    def get_entity(self, sg_item):
        """
        Gets the most specific entity and context from an sg_item.
        Prioritizes Task context over Asset/Shot context.
        """
        if not sg_item:
            return None

        entity, published_file = self.parent.get_entity_from_sg_item(sg_item)
        if not entity:
            return sg_item

        sg_item["entity"] = entity
        context_entity = entity
        task = published_file.get("task")

        # Prioritize Task for context if it exists
        if isinstance(task, dict) and task.get("type") == "Task" and task.get("id"):
            context_entity = task
            logger.debug(f"Prioritizing Task context for {context_entity}")

        entity_type = context_entity.get("type")
        entity_id = context_entity.get("id")

        if entity_type and entity_id:
            context_key = (entity_type, entity_id)
            if context_key not in self.context_cache:
                try:
                    tk = sgtk.sgtk_from_entity(entity_type, entity_id)
                    context = tk.context_from_entity(entity_type, entity_id)
                    self.context_cache[context_key] = str(context)
                except Exception as e:
                    logger.debug(f"Failed to retrieve context for {entity_type} {entity_id}: {e}")
                    self.context_cache[context_key] = "Context Error"
            sg_item["context"] = self.context_cache[context_key]

        return sg_item

    # --- Context Menu for Changing Context ---

    def _show_files_table_context_menu(self, pos):
        """Shows a context menu on right-click if rows are selected."""
        if not self.files_table_widget.selectionModel().hasSelection():
            return

        menu = QtGui.QMenu(self)
        change_context_action = menu.addAction("Change Context...")
        change_context_action.triggered.connect(self._on_change_context_triggered)
        menu.exec_(self.files_table_widget.viewport().mapToGlobal(pos))

    def _on_change_context_triggered(self):
        """Launches the ShotGrid Search Widget to select a new context."""
        selected_rows = self.files_table_widget.selectionModel().selectedRows()
        if not selected_rows:
            return

        shotgun_search_widget = sgtk.platform.import_framework(
            "tk-framework-qtwidgets", "shotgun_search_widget"
        )
        dialog = QtGui.QDialog(self)
        dialog.setWindowTitle("Select a New Context")
        dialog.setMinimumSize(500, 400)
        layout = QtGui.QVBoxLayout(dialog)
        search_widget = shotgun_search_widget.SearchWidget(dialog)
        search_widget.set_search_entity_types(["Asset", "Shot", "Sequence", "Task"])
        search_widget.set_placeholder_text("Search for an Asset, Shot, or Task...")

        # Connect the selection signal to our handler
        search_widget.entity_selected.connect(
            lambda et, eid, en: self._apply_new_context(et, eid, en, selected_rows, dialog)
        )
        layout.addWidget(search_widget)
        dialog.exec_()

    def _apply_new_context(self, entity_type, entity_id, entity_name, selected_rows, dialog):
        """Applies the selected context to the files selected in the table."""
        logger.debug(f"Applying new context: {entity_type} {entity_id} ('{entity_name}')")
        try:
            tk = sgtk.sgtk_from_entity(entity_type, entity_id)
            new_context = tk.context_from_entity(entity_type, entity_id)
            new_context_str = str(new_context)
            new_entity_dict = {"type": entity_type, "id": entity_id, "name": entity_name}

            for model_index in selected_rows:
                row = model_index.row()
                file_item = self.files_table_widget.item(row, 1)
                if not file_item:
                    continue
                dict_key = file_item.data(QtCore.Qt.UserRole)
                if not dict_key or dict_key not in self.submit_widget_dict:
                    logger.warning(f"Could not find data for row {row}. Skipping context update.")
                    continue

                # Update the underlying data dictionary
                sg_item = self.submit_widget_dict[dict_key].setdefault("sg_item", {})
                sg_item["entity"] = new_entity_dict
                sg_item["context"] = new_context_str

                # Update the UI table
                self.files_table_widget.item(row, 7).setText(entity_name)
                self.files_table_widget.item(row, 8).setText(str(entity_id))
                self.files_table_widget.item(row, 9).setText(new_context_str)
                self.files_table_widget.item(row, 10).setText("Entity is recognizable")

                # Update tooltips and reset text color
                for col in range(self.files_table_widget.columnCount()):
                    item = self.files_table_widget.item(row, col)
                    if item:
                        item.setToolTip(item.text())
                        item.setForeground(QtGui.QApplication.style().standardPalette().color(QtGui.QPalette.Text))

            dialog.accept()
        except Exception as e:
            logger.error(f"Failed to apply new context: {e}", exc_info=True)
            QtGui.QMessageBox.critical(self, "Error", f"Failed to apply new context: {e}")
            dialog.reject()

        self.update_buttons_state()

    # --- UI Action Handlers ---

    def update_buttons_state(self):
        """Enables or disables buttons based on the current state."""
        description_ok = len(self.changelist_description.toPlainText()) >= 5
        has_submittable_files = any(
            self.files_table_widget.item(row, 0).checkState() == QtCore.Qt.Checked and
            "not recognized" not in self.files_table_widget.item(row, 10).text()
            for row in range(self.files_table_widget.rowCount())
        )
        self.submit_button.setEnabled(description_ok and has_submittable_files)
        self.save_button.setEnabled(description_ok)

    def select_all(self):
        """Checks all checkboxes in the table."""
        for row in range(self.files_table_widget.rowCount()):
            self.files_table_widget.item(row, 0).setCheckState(QtCore.Qt.Checked)
        self.update_buttons_state()

    def select_none(self):
        """Unchecks all checkboxes in the table."""
        for row in range(self.files_table_widget.rowCount()):
            self.files_table_widget.item(row, 0).setCheckState(QtCore.Qt.Unchecked)
        self.update_buttons_state()

    def submit_changelist(self):
        """Gathers selected files and passes them to the parent for submission."""
        description = self.changelist_description.toPlainText()
        file_info_deleted = []
        file_info_other = []

        for row in range(self.files_table_widget.rowCount()):
            if self.files_table_widget.item(row, 0).checkState() == QtCore.Qt.Checked:
                dict_key = self.files_table_widget.item(row, 1).data(QtCore.Qt.UserRole)
                if dict_key in self.submit_widget_dict:
                    full_file_info = self.submit_widget_dict[dict_key]
                    sg_item = full_file_info.get("sg_item", {})
                    sg_item["description"] = description
                    action = full_file_info.get("pending_action")
                    if action == "delete":
                        file_info_deleted.append(full_file_info)
                    else:
                        file_info_other.append(full_file_info)

        if not file_info_deleted and not file_info_other:
            QtGui.QMessageBox.warning(self, "Warning", "No valid files selected for submission.")
            return

        if file_info_deleted:
            self.parent.on_submit_deleted_files(self.change_sg_item, file_info_deleted)
        if file_info_other:
            self.parent.on_submit_other_files(self.change_sg_item, file_info_other)

        self.parent._add_log("\n <span style='color:#2C93E2'>Updating the Pending view...</span> \n", 2)
        self.parent._populate_pending_widget()
        self.parent._on_treeview_item_selected()
        self.accept()

    def save_changelist(self):
        """Saves the changelist description via Perforce."""
        description = self.changelist_description.toPlainText()
        change_id = self.changelist_value.text()
        try:
            changelist_spec = self.p4.fetch_change(change_id)
            changelist_spec['Description'] = description
            self.p4.save_change(changelist_spec)
            logger.debug(f"Changelist {change_id} saved successfully.")
            self.parent._add_log("\n <span style='color:#2C93E2'>Updating the Pending view...</span> \n", 2)
            self.parent._populate_pending_widget()
            self.accept()
        except Exception as e:
            logger.error(f"Failed to save changelist {change_id}: {e}", exc_info=True)
            QtGui.QMessageBox.critical(self, "Error", f"Failed to save changelist: {e}")

    def cancel_action(self):
        """Closes the dialog without taking action."""
        self.reject()

    # --- Utility and Helper Methods ---

    def _create_item_with_tooltip(self, text):
        """Creates a QTableWidgetItem and sets its tooltip to its text."""
        str_text = str(text) if text is not None else ""
        item = QtGui.QTableWidgetItem(str_text)
        item.setToolTip(str_text)
        return item

    def _fix_timestamp(self, unix_timestamp):
        """Converts a Unix timestamp to a human-readable string."""
        try:
            ts = int(unix_timestamp)
            dt = datetime.datetime.fromtimestamp(ts, shotgun_api3.sg_timezone.LocalTimezone())
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError, OSError):
            return "N/A"

    def _sort_key_func(self, item):
        """Provides a key for sorting files, primarily by source changelist."""
        key, file_info_val = item
        sg_item = file_info_val.get("sg_item", {})
        head_change = sg_item.get("headChange")
        if head_change is None or head_change == 'default':
            return ('z_default', key)  # Sort default CL last
        try:
            return (int(head_change), key)
        except (ValueError, TypeError):
            return (str(head_change), key)

"""
TechDeck Plugin Settings Widget
Dynamically generates settings UI from plugin schema with real-time validation.
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QPushButton, QFileDialog, QFrame
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QRegularExpressionValidator


class PluginSettingsWidget(QWidget):
    """
    Dynamically generates settings UI from plugin schema.
    
    Supports field types:
    - string: QLineEdit with optional regex validation
    - number: QSpinBox/QDoubleSpinBox
    - boolean: QCheckBox
    - choice: QComboBox
    - file: QLineEdit + Browse button
    - directory: QLineEdit + Browse button
    
    Signals:
        settings_changed(): Emitted when any setting changes
        validation_changed(bool): Emitted when validation state changes
    """
    
    settings_changed = Signal()
    validation_changed = Signal(bool)
    
    def __init__(self, plugin_id: str, schema: Dict[str, Any], current_values: Dict[str, Any], parent=None):
        """
        Initialize plugin settings widget.
        
        Args:
            plugin_id: Plugin identifier
            schema: Settings schema from plugin.json
            current_values: Currently saved values
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.plugin_id = plugin_id
        self.schema = schema
        self.current_values = current_values
        self.widgets: Dict[str, QWidget] = {}
        self.validators: Dict[str, Callable[[], bool]] = {}
        
        self._create_ui()
    
    def _create_ui(self):
        """Create the dynamic settings UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # Get fields from schema
        fields = self.schema.get('fields', [])
        
        if not fields:
            no_settings_label = QLabel("This plugin has no configurable settings.")
            no_settings_label.setStyleSheet("color: #888; font-style: italic;")
            layout.addWidget(no_settings_label)
            return
        
        # Create widget for each field
        for field in fields:
            field_widget = self._create_field_widget(field)
            if field_widget:
                layout.addWidget(field_widget)
        
        # Add stretch at bottom
        layout.addStretch()
    
    def _create_field_widget(self, field: Dict[str, Any]) -> Optional[QWidget]:
        """Create a widget for a field based on its type."""
        field_type = field.get('type', 'string')
        field_key = field.get('key')
        
        if not field_key:
            return None
        
        # Container for field
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(6)
        
        # Label with required indicator
        label_text = field.get('label', field_key)
        if field.get('required', False):
            label_text += " *"
        
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: 600;")
        container_layout.addWidget(label)
        
        # Create input widget based on type
        input_widget = None
        
        if field_type == 'string':
            input_widget = self._create_string_field(field)
        elif field_type == 'number':
            input_widget = self._create_number_field(field)
        elif field_type == 'boolean':
            input_widget = self._create_boolean_field(field)
        elif field_type == 'choice':
            input_widget = self._create_choice_field(field)
        elif field_type == 'file':
            input_widget = self._create_file_field(field)
        elif field_type == 'directory':
            input_widget = self._create_directory_field(field)
        
        if input_widget:
            container_layout.addWidget(input_widget)
            self.widgets[field_key] = input_widget
            
            # Add description/help text if provided
            description = field.get('description')
            if description:
                desc_label = QLabel(description)
                desc_label.setStyleSheet("color: #888; font-size: 12px;")
                desc_label.setWordWrap(True)
                container_layout.addWidget(desc_label)
            
            # Add validation error label (hidden by default)
            error_label = QLabel()
            error_label.setStyleSheet("color: #EF4444; font-size: 12px; margin-top: 2px;")
            error_label.setVisible(False)
            error_label.setObjectName(f"{field_key}_error")
            container_layout.addWidget(error_label)
            
            # Setup validator if needed
            self._setup_validator(field, input_widget, error_label)
        
        return container
    
    def _create_string_field(self, field: Dict[str, Any]) -> QLineEdit:
        """Create string input field."""
        field_key = field['key']
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(field.get('placeholder', ''))
        line_edit.setMinimumHeight(34)
        
        # Set current value
        current_value = self.current_values.get(field_key, field.get('default', ''))
        line_edit.setText(str(current_value))
        
        # Connect change signal
        line_edit.textChanged.connect(self._on_value_changed)
        
        return line_edit
    
    def _create_number_field(self, field: Dict[str, Any]) -> QWidget:
        """Create number input field."""
        field_key = field['key']
        default_value = field.get('default', 0)
        
        # Determine if float or int
        is_float = isinstance(default_value, float) or field.get('step', 1) != int(field.get('step', 1))
        
        if is_float:
            spin_box = QDoubleSpinBox()
        else:
            spin_box = QSpinBox()
        
        spin_box.setMinimumHeight(34)
        spin_box.setMinimum(field.get('min', -999999))
        spin_box.setMaximum(field.get('max', 999999))
        spin_box.setSingleStep(field.get('step', 1))
        
        # Set suffix if provided
        suffix = field.get('suffix', '')
        if suffix:
            spin_box.setSuffix(suffix)
        
        # Set current value
        current_value = self.current_values.get(field_key, default_value)
        spin_box.setValue(current_value)
        
        # Connect change signal
        spin_box.valueChanged.connect(self._on_value_changed)
        
        return spin_box
    
    def _create_boolean_field(self, field: Dict[str, Any]) -> QCheckBox:
        """Create boolean checkbox field."""
        field_key = field['key']
        checkbox = QCheckBox(field.get('description', ''))
        
        # Set current value
        current_value = self.current_values.get(field_key, field.get('default', False))
        checkbox.setChecked(bool(current_value))
        
        # Connect change signal
        checkbox.stateChanged.connect(self._on_value_changed)
        
        return checkbox
    
    def _create_choice_field(self, field: Dict[str, Any]) -> QComboBox:
        """Create choice dropdown field."""
        field_key = field['key']
        combo_box = QComboBox()
        combo_box.setMinimumHeight(34)
        
        # Add options
        options = field.get('options', [])
        for option in options:
            if isinstance(option, dict):
                combo_box.addItem(option.get('label', ''), option.get('value'))
            else:
                combo_box.addItem(str(option), option)
        
        # Set current value
        current_value = self.current_values.get(field_key, field.get('default'))
        index = combo_box.findData(current_value)
        if index >= 0:
            combo_box.setCurrentIndex(index)
        
        # Connect change signal
        combo_box.currentIndexChanged.connect(self._on_value_changed)
        
        return combo_box
    
    def _create_file_field(self, field: Dict[str, Any]) -> QWidget:
        """Create file path field with browse button."""
        field_key = field['key']
        
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        line_edit = QLineEdit()
        line_edit.setMinimumHeight(34)
        line_edit.setObjectName(f"{field_key}_input")
        
        # Set current value
        current_value = self.current_values.get(field_key, field.get('default', ''))
        line_edit.setText(str(current_value))
        
        # Connect change signal
        line_edit.textChanged.connect(self._on_value_changed)
        
        # Browse button
        browse_btn = QPushButton("Browse")
        browse_btn.setMinimumHeight(34)
        browse_btn.setMaximumWidth(100)
        
        def browse_file():
            filters = field.get('filters', 'All Files (*.*)')
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                f"Select {field.get('label', 'File')}",
                line_edit.text() or str(Path.home()),
                filters
            )
            if file_path:
                line_edit.setText(file_path)
        
        browse_btn.clicked.connect(browse_file)
        
        layout.addWidget(line_edit, 1)
        layout.addWidget(browse_btn)
        
        return container
    
    def _create_directory_field(self, field: Dict[str, Any]) -> QWidget:
        """Create directory path field with browse button."""
        field_key = field['key']
        
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        line_edit = QLineEdit()
        line_edit.setMinimumHeight(34)
        line_edit.setObjectName(f"{field_key}_input")
        
        # Set current value
        current_value = self.current_values.get(field_key, field.get('default', ''))
        line_edit.setText(str(current_value))
        
        # Connect change signal
        line_edit.textChanged.connect(self._on_value_changed)
        
        # Browse button
        browse_btn = QPushButton("Browse")
        browse_btn.setMinimumHeight(34)
        browse_btn.setMaximumWidth(100)
        
        def browse_dir():
            dir_path = QFileDialog.getExistingDirectory(
                self,
                f"Select {field.get('label', 'Directory')}",
                line_edit.text() or str(Path.home())
            )
            if dir_path:
                line_edit.setText(dir_path)
        
        browse_btn.clicked.connect(browse_dir)
        
        layout.addWidget(line_edit, 1)
        layout.addWidget(browse_btn)
        
        return container
    
    def _setup_validator(self, field: Dict[str, Any], widget: QWidget, error_label: QLabel):
        """Setup validation for a field."""
        field_key = field['key']
        field_type = field.get('type', 'string')
        required = field.get('required', False)
        
        def validate() -> bool:
            """Validate the field value."""
            value = self._get_widget_value(field_key, widget, field_type)
            
            # Check required
            if required and not value:
                error_label.setText("This field is required")
                error_label.setVisible(True)
                widget.setStyleSheet("border: 1px solid #EF4444; border-radius: 6px;")
                return False
            
            # Check string validation pattern
            if field_type == 'string' and value:
                validation = field.get('validation', {})
                pattern = validation.get('pattern')
                if pattern:
                    if not re.match(pattern, str(value)):
                        error_label.setText(validation.get('message', 'Invalid format'))
                        error_label.setVisible(True)
                        widget.setStyleSheet("border: 1px solid #EF4444; border-radius: 6px;")
                        return False
            
            # Valid
            error_label.setVisible(False)
            widget.setStyleSheet("")
            return True
        
        # Store validator
        self.validators[field_key] = validate
        
        # Run initial validation
        validate()
    
    def _get_widget_value(self, field_key: str, widget: QWidget, field_type: str) -> Any:
        """Get value from a widget based on field type."""
        if field_type == 'string':
            return widget.text() if isinstance(widget, QLineEdit) else ""
        elif field_type == 'number':
            return widget.value() if isinstance(widget, (QSpinBox, QDoubleSpinBox)) else 0
        elif field_type == 'boolean':
            return widget.isChecked() if isinstance(widget, QCheckBox) else False
        elif field_type == 'choice':
            return widget.currentData() if isinstance(widget, QComboBox) else None
        elif field_type in ('file', 'directory'):
            # Find the line edit inside the container
            line_edit = widget.findChild(QLineEdit, f"{field_key}_input")
            return line_edit.text() if line_edit else ""
        
        return None
    
    def _on_value_changed(self):
        """Handle value change in any field."""
        # Revalidate all fields
        self.validate_all()
        
        # Emit change signal
        self.settings_changed.emit()
    
    def validate_all(self) -> bool:
        """
        Validate all fields.
        
        Returns:
            True if all fields are valid
        """
        all_valid = True
        
        for field_key, validator in self.validators.items():
            if not validator():
                all_valid = False
        
        self.validation_changed.emit(all_valid)
        return all_valid
    
    def get_values(self) -> Dict[str, Any]:
        """
        Get all field values.
        
        Returns:
            Dictionary of field_key: value
        """
        values = {}
        
        # Get field types from schema
        field_types = {
            field['key']: field.get('type', 'string')
            for field in self.schema.get('fields', [])
        }
        
        for field_key, widget in self.widgets.items():
            field_type = field_types.get(field_key, 'string')
            values[field_key] = self._get_widget_value(field_key, widget, field_type)
        
        return values
    
    def get_defaults(self) -> Dict[str, Any]:
        """
        Get default values from schema.
        
        Returns:
            Dictionary of field_key: default_value
        """
        defaults = {}
        
        for field in self.schema.get('fields', []):
            field_key = field.get('key')
            if field_key:
                defaults[field_key] = field.get('default')
        
        return defaults

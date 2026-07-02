"""
Nest Selection Dialog
======================
Modal dialog shown by 911 Setup after the user enters a batch number. It
displays the batch as a tree: a checkable batch-folder root with one checkable
child per nest in the batch. Checking/unchecking the root toggles every nest;
individual nests can be toggled freely.

Nests that already have a folder in the batch are marked "already set up" so the
operator can tell a fresh run from a re-run at a glance. The dialog returns the
list of nests the user chose to run, or None if they cancelled.

This is now a thin wrapper over the generic ``SelectionDialog`` (the layout the
922 Batch Repeater also uses) that supplies the 911-specific wording.
"""

from techdeck.ui.dialogs.selection_dialog import SelectionDialog


class NestSelectionDialog(SelectionDialog):
    """Tree of batch -> nests with checkboxes. selected_nests() returns the picks."""

    def __init__(self, batch_number, all_nests, existing_nests=None, parent=None):
        super().__init__(
            all_nests,
            existing_nests,
            parent=parent,
            window_title=f"911 Setup - Batch {batch_number}",
            header="Select Nests to Run",
            root_label=f"Batch {batch_number}  (all nests)",
            noun="nest",
            done_label="already set up",
            prompt_note="Check the nests you want to set up.",
            subhead_prefix=f"Batch {batch_number} - ",
            default_checked=False,  # 911 Setup starts with everything unchecked
        )

    def selected_nests(self):
        """Return checked nests in their original batch-list order."""
        return self.selected()

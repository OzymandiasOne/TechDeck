# 902 DXF Prep, Workflow Guide

This guide maps the original SOP ("Batch DXF Cleanup and Preparation for Boost 902
Part Files") to the three processes in the TechDeck 902 DXF Prep app. The SigmaNest
and AutoCAD segments stay manual; TechDeck automates everything on either side of
them.

## Before You Start (one time machine setup, not part of TechDeck)

* Update Windows settings to allow opening up to 25 DXF files at once in AutoCAD.
* Enable the DXF autosave option in AutoCAD.
* Create the AutoCAD cleanup macro: ZOOM Extent, then QSELECT for objects on
  Layer 12, then change diameter to 0.012", then SAVE. Create a 0.017" circle on
  Layer 12 in your default template first to support the macro.

## TechDeck Process 1: Setup (IGES CONVERT folder + QTY sheet)

What TechDeck does here: you pick the folder that holds the part files, and
TechDeck copies any IGES files it finds there into a new "BATCH# - IGES CONVERT"
folder in the batch folder, then builds "BATCH# QTY.xlsx" next to the PO
spreadsheet (parts sorted, repeated part numbers boxed, multiple quantity parts
highlighted, plus a NOTES column for documenting exceptions). If the selected
folder has no IGES files, the copy is skipped with a note and the QTY sheet is
still built. An existing QTY workbook is never overwritten, so your notes survive
a rerun.

Covers these SOP steps:

1. Create the working folder; make a new folder named "BATCH# - IGES CONVERT"
   in the batch folder (for example "3030 - IGES CONVERT").
2. Copy the IGES files; copy only the .igs files into the new folder, leaving
   the uncleaned EB DXF files behind.
3. Prepare the quantity spreadsheet; open the PO spreadsheet, create a QTY
   sheet, copy the DYPN through Qty columns, delete the extra columns and rows,
   make a table, sort by part number, apply borders around repeating part
   numbers, and highlight parts with multiple quantities.

## Manual Segment: SigmaNest VM (TechDeck cannot reach the RDP machine)

Do this between Process 1 and Process 2.

4. Transfer to the virtual machine; copy the "BATCH# - IGES CONVERT" folder into
   the SigmaNest RDP virtual machine.
5. Import into SigmaNest; create or load a workspace and import all the IGES
   files from the transferred folder.
6. Interactive Mapping; when the dialog appears, select "IGES IMPORT AL" next to
   the Desktop option.
7. Review and validate parts; check for any files showing a red X or unchecked
   status. For parts without a green check, compare the file layers against the
   part print and activate the correct layers. If the print is unavailable or
   the layers do not match, document the part number on the QTY spreadsheet.
8. Complete the import; after reviewing all parts click OK, then click OK in the
   Part Parameters dialog without changes.
9. Advanced Export to DXF; go to Files, Export, Advanced Export. On the Files to
   Export page open Configuration, browse to the IGES folder on the VM, create a
   new subfolder named "BATCH# - DXF", and save to that location without
   changing other export settings. Confirm the location, return to Files to
   Export, click Export, and watch the progress bar. Document any error messages
   with part numbers on the QTY spreadsheet.
10. Return the files; once the export completes, move the "BATCH# - DXF" folder
    (only) back to the original SharePoint batch folder.

## TechDeck Process 2: Rename + Sort

What TechDeck does here: strips "_FLAT-PATTERN#1", revision letters, and trailing
numbers from every DXF filename in the selected folder, then splits the files
into numbered subfolders of 25 each for the AutoCAD pass. Filenames it cannot
recognize are left alone and flagged in the console; document those on the QTY
spreadsheet. It refuses to sort a folder that already has numbered subfolders, so
it cannot double sort.

Covers these SOP steps (previously the "filerenamer v4" and
"folder_file_sorter_02" scripts):

11. Rename the files; remove "_FLAT-PATTERN#1" and any part revision letters or
    numbers from the filenames in the DXF folder.
12. Sort into numbered folders; split the files into numbered subfolders
    containing 25 part files each.

## Manual Segment: AutoCAD Review and Cleanup

Do this between Process 2 and Process 3, one numbered folder at a time.

13. Open the 25 DXF files in a folder. Review each file for Layer 12; close any
    file that does not contain it. Expected layers are Layer 111 (always) and
    Layer 17 (frequently); for files missing expected layers, note the part
    number on the QTY spreadsheet and cross reference the part print or the
    original DXF. When Layer 12 is present, run the prepared macro, save the
    file (an extra manual save is recommended), and close it. Repeat until all
    numbered folders are processed.

## TechDeck Process 3: Recombine + Verify

What TechDeck does here: merges the numbered subfolders back into the main
folder, then reconciles the files against the PO spreadsheet in both directions.
Parts on the spreadsheet with no file are written to "BATCH# - MISSING PARTS.txt"
in the batch folder; files not on the spreadsheet move to an EXTRA subfolder
(relocated, never deleted); parts ordered more than once get a quantity prefix on
the filename, for example "(18x) H4130810-484.dxf".

Covers these SOP steps (previously the "folder_file_undo_02" script plus a manual
cross reference):

14. Recombine the folders; remove the numbered subfolders and merge all files
    back into the main DXF folder.
15. Final verification; cross reference all part files against the QTY
    spreadsheet, confirm the set of parts is complete, and append quantities to
    the beginning of filenames for parts with multiples.

## Notes on Running the Processes

* On launch the app asks you to pick the folder that contains the part files
  (the DXF export folder, or the mixed folder holding IGES and DXF together),
  then shows the process picker with all three processes checked.
* Selected processes run in order with no breaks between them; if one fails, the
  remaining ones are skipped and the console says why.
* The normal cadence across a batch is Process 1, then the SigmaNest VM work,
  then Process 2, then the AutoCAD pass, then Process 3.
* Running Process 2 and Process 3 together sorts the files and then immediately
  recombines them; the net effect is rename plus verify with no numbered folders
  left behind. Useful when the AutoCAD pass is already done or not needed.
* Every process is safe to rerun; reruns skip work that is already done (IGES
  files already copied, filenames already clean, prefixes already applied).
* Per the SOP, document all exceptions, errors, and nonstandard parts on the QTY
  spreadsheet; the generated workbook has a NOTES column for exactly that.

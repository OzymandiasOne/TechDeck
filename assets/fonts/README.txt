Drop the FOT Bokutoh Pro font here (.otf or .ttf).

It is loaded at runtime by techdeck/ui/widgets/moth_widget.py (haiku_font) for
the /moth haiku speech bubble. The loader registers every .otf/.ttf/.ttc in this
folder and prefers the family whose name contains "Bokutoh". Until the file is
present, the bubble falls back to a default italic face.

The whole assets/ tree is bundled into the build (see TechDeck.spec datas), so a
font placed here ships with the installer automatically.

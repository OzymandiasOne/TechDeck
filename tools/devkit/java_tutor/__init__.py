"""Java Tutor — a personal Java-coaching chat window, mounted in the DevKit.

It lived in `plugins/` until 2026-09-02 and was kept out of the installer by
two `Excludes:` patterns in TechDeck-Setup.iss. That was string matching: a
renamed folder or a reworded pattern would have shipped it silently. Under
`tools/` it cannot ship at all — `TechDeck.spec` excludes the whole `tools`
package from every frozen build, so "never ships" is now a property of the
build rather than a rule someone has to keep restating.
"""

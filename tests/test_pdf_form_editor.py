from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pdf_form_editor import (  # noqa: E402
    DND2024_RU_PROFILE,
    DND5E_2014_RU_PROFILE,
    PdfFormEditor,
    normalize_text,
)


class NormalizeTextTests(unittest.TestCase):
    def test_normalize_text_rewrites_problem_glyphs_to_pdf_safe_ascii(self) -> None:
        self.assertEqual(
            normalize_text("• “умно” — и\r\nбез сюрпризов"),
            '- "умно" - и\nбез сюрпризов',
        )


class LocalizedDndTemplateTests(unittest.TestCase):
    def test_dnd5e_2014_ru_profile_maps_logical_skill_rows_and_checkboxes(self) -> None:
        editor = PdfFormEditor(ROOT / "templates" / "DnD_5E_CharacterSheet_Form_Fillable_ru.pdf")
        self.addCleanup(editor.close)

        self.assertEqual(editor.template_profile, DND5E_2014_RU_PROFILE)

        editor.set_skill_values({"Performance": "+2"})
        self.assertEqual(editor.field_value("Performance"), "+2")
        self.assertEqual(editor.field_value("raw:History "), "+2")

        editor.set_skill_proficiencies({"Performance": True})
        self.assertTrue(editor.checkbox_checked("skill_prof:Performance"))
        self.assertTrue(editor.checkbox_checked("raw:Check Box 28"))

    def test_raw_prefix_bypasses_dnd5e_2014_logical_skill_remap(self) -> None:
        editor = PdfFormEditor(ROOT / "templates" / "DnD_5E_CharacterSheet_Form_Fillable_ru.pdf")
        self.addCleanup(editor.close)

        editor.set_text("raw:Performance", "+7")
        self.assertEqual(editor.field_value("raw:Performance"), "+7")
        self.assertEqual(editor.field_value("Performance"), "")

    def test_dnd2024_ru_profile_maps_logical_skill_rows_and_checkboxes(self) -> None:
        editor = PdfFormEditor(ROOT / "templates" / "DnD_2024_Character-Sheet-Fillable-RUS.pdf")
        self.addCleanup(editor.close)

        self.assertEqual(editor.template_profile, DND2024_RU_PROFILE)

        editor.set_skill_values({"Persuasion": "+4"})
        self.assertEqual(editor.field_value("Persuasion"), "+4")
        self.assertEqual(editor.field_value("raw:text_77nads"), "+4")

        editor.set_skill_proficiencies({"Persuasion": True})
        self.assertTrue(editor.checkbox_checked("skill_prof:Persuasion"))
        self.assertTrue(editor.checkbox_checked("raw:checkbox_255ltdr"))

    def test_dnd5e_2014_ru_exposes_expected_image_button_fields(self) -> None:
        editor = PdfFormEditor(ROOT / "templates" / "DnD_5E_CharacterSheet_Form_Fillable_ru.pdf")
        self.addCleanup(editor.close)

        self.assertEqual(
            editor.button_field_names(),
            ["CHARACTER IMAGE", "Faction Symbol Image"],
        )
        self.assertEqual(editor.default_image_field_name(), "CHARACTER IMAGE")

    def test_dnd2024_ru_exposes_no_image_button_fields(self) -> None:
        editor = PdfFormEditor(ROOT / "templates" / "DnD_2024_Character-Sheet-Fillable-RUS.pdf")
        self.addCleanup(editor.close)

        self.assertEqual(editor.button_field_names(), [])
        self.assertIsNone(editor.default_image_field_name())


if __name__ == "__main__":
    unittest.main()

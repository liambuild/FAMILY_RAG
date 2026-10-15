"""Tests de caractérisation du StructureAwareSplitter.

Les tests « golden » figent la sortie actuelle. Les bugs connus sont décrits par
des tests `xfail(strict=True)` qui expriment le comportement attendu : quand le
lot indiqué corrige le bug, le xfail passe et doit être retiré (AUDIT.md §6).
"""

import pytest
from langchain_core.documents import Document

from structure_aware_splitter import StructureAwareSplitter

META = {"source": "note.txt", "file_type": "txt"}


def split(text: str, **kwargs) -> list:
    splitter = StructureAwareSplitter(**kwargs)
    return splitter.split_documents([Document(page_content=text, metadata=dict(META))])


# --- Texte sans structure : repli sur le splitter classique -------------------

class TestPlainText:
    def test_short_text_is_one_identical_chunk(self):
        chunks = split("Une phrase simple, sans structure particulière.")
        assert [c.page_content for c in chunks] == ["Une phrase simple, sans structure particulière."]
        assert chunks[0].metadata == META

    def test_long_text_is_cut_to_chunk_size_and_keeps_metadata(self):
        text = "\n\n".join(f"Paragraphe numéro {i} avec un peu de texte." for i in range(20))
        chunks = split(text, chunk_size=120, chunk_overlap=20)
        assert len(chunks) > 1
        assert all(len(c.page_content) <= 120 for c in chunks)
        assert all(c.metadata == META for c in chunks)

    def test_empty_document_gives_no_chunk(self):
        assert split("") == []


# --- Sections -----------------------------------------------------------------

SECTIONS = "# Titre A\ncontenu A\n\n# Titre B\ncontenu B"


class TestSections:
    def test_small_document_stays_in_one_chunk_without_section_metadata(self):
        chunks = split(SECTIONS)
        assert len(chunks) == 1
        assert chunks[0].page_content == "# Titre A\ncontenu A\n\n# Titre B\ncontenu B"
        assert "section" not in chunks[0].metadata

    def test_sections_are_detected(self):
        splitter = StructureAwareSplitter()
        for text in ("# Titre\ntexte", "Article 1 Objet\ntexte", "Chapitre 2 Suite\ntexte", "I. Premier\ntexte"):
            assert splitter._has_sections(text), text

    def test_section_metadata_is_the_title_of_the_next_section(self):
        """Caractérisation de F12 : le chunk sauvegardé reçoit le titre suivant."""
        chunks = split(SECTIONS, max_chunk_size=20, chunk_overlap=5)
        assert len(chunks) == 2
        assert chunks[0].page_content == "# Titre A\ncontenu A"
        assert chunks[0].metadata["section"] == "# Titre B"
        assert "section" not in chunks[-1].metadata

    @pytest.mark.xfail(reason="F12 : la section d'un chunk est celle de la section suivante (lot 6)")
    def test_section_metadata_is_the_chunk_own_title(self):
        chunks = split(SECTIONS, max_chunk_size=20, chunk_overlap=5)
        assert chunks[0].metadata["section"] == "# Titre A"
        assert chunks[-1].metadata["section"] == "# Titre B"

    def test_numbered_list_with_lowercase_items_is_treated_as_sections(self):
        """Caractérisation de F13 : « 1. texte » est pris pour un titre (lot 6)."""
        splitter = StructureAwareSplitter()
        assert splitter._has_sections("1. acheter du pain\n2. acheter du lait\n3. acheter du beurre")

    def test_chunk_size_is_ignored_in_structured_paths(self):
        """Caractérisation de F14 : seul max_chunk_size compte (lot 6)."""
        body = "mot " * 100  # 400 caractères
        chunks = split(f"# Titre\n{body}", chunk_size=100, chunk_overlap=10)
        assert len(chunks) == 1
        assert len(chunks[0].page_content) > 100


# --- Listes -------------------------------------------------------------------

LISTE = "Courses de la semaine\n\n- pommes\n- poires\n- cerises\n\nFin de la liste."


class TestLists:
    def test_bullet_list_is_detected(self):
        splitter = StructureAwareSplitter()
        assert splitter._has_numbered_list(LISTE)
        assert not splitter._has_sections(LISTE)

    def test_list_block_is_duplicated(self):
        """Caractérisation de F2 : le bloc de liste apparaît deux fois."""
        chunks = split(LISTE)
        assert len(chunks) == 1
        assert chunks[0].page_content.count("- pommes\n- poires\n- cerises") == 2

    @pytest.mark.xfail(reason="F2 : listes dupliquées dans les chunks (lot 6)")
    def test_list_block_appears_once(self):
        chunks = split(LISTE)
        assert sum(c.page_content.count("- pommes\n- poires\n- cerises") for c in chunks) == 1


# --- Tableaux -----------------------------------------------------------------

TABLEAU = "Introduction du relevé\n\n| nom | montant |\n| loyer | 800 |\n\nConclusion du relevé"


class TestTables:
    def test_table_is_detected(self):
        splitter = StructureAwareSplitter()
        assert splitter._has_table(TABLEAU)
        assert not splitter._has_sections(TABLEAU)
        assert not splitter._has_numbered_list(TABLEAU)

    def test_table_is_isolated_in_a_flagged_chunk(self):
        chunks = split(TABLEAU)
        table_chunks = [c for c in chunks if c.metadata.get("contains_table")]
        assert table_chunks
        assert all(c.page_content == "| nom | montant |\n| loyer | 800 |" for c in table_chunks)
        assert chunks[0].page_content == "Introduction du relevé"
        assert all(c.metadata["source"] == "note.txt" for c in chunks)

    def test_table_chunk_is_duplicated(self):
        """Caractérisation de F2 : le tableau donne deux chunks identiques."""
        chunks = split(TABLEAU)
        assert len([c for c in chunks if c.metadata.get("contains_table")]) == 2

    @pytest.mark.xfail(reason="F2 : tableaux dupliqués dans les chunks (lot 6)")
    def test_table_chunk_appears_once(self):
        chunks = split(TABLEAU)
        assert len([c for c in chunks if c.metadata.get("contains_table")]) == 1

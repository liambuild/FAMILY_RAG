"""Splitter intelligent qui préserve la structure des documents."""

import re
from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class StructureAwareSplitter:
    """Découpe intelligente qui préserve la structure sémantique des documents.

    Contrairement au RecursiveCharacterTextSplitter qui découpe à taille fixe,
    ce splitter détecte et préserve les structures logiques :
    - Sections (titres, articles, chapitres)
    - Listes numérotées/à puces
    - Tableaux
    - Paragraphes cohérents
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
        max_chunk_size: int = 2000
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size

        # Fallback sur le splitter classique
        self.fallback_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """Découpe une liste de documents en préservant la structure."""
        all_chunks = []

        for doc in documents:
            chunks = self._split_single_document(doc)
            all_chunks.extend(chunks)

        return all_chunks

    def _split_single_document(self, doc: Document) -> List[Document]:
        """Découpe un document unique."""
        content = doc.page_content

        # Détecter le type de structure
        if self._has_sections(content):
            return self._split_by_sections(doc)
        elif self._has_numbered_list(content):
            return self._split_by_lists(doc)
        elif self._has_table(content):
            return self._split_preserve_tables(doc)
        else:
            # Fallback : découpage classique
            return self.fallback_splitter.split_documents([doc])

    def _has_sections(self, content: str) -> bool:
        """Détecte si le document contient des sections (titres, articles)."""
        patterns = [
            r'^#+\s+',  # Markdown headers (# Title)
            r'^Article\s+\d+',  # Article 1, Article 2
            r'^Section\s+\d+',  # Section 1, Section 2
            r'^Chapitre\s+\d+',  # Chapitre 1, Chapitre 2
            r'^[IVX]+\.\s+',  # I. II. III. (nombres romains)
            r'^\d+\.\s+[A-Z]',  # 1. TITRE EN MAJUSCULES
        ]

        for pattern in patterns:
            if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
                return True
        return False

    def _has_numbered_list(self, content: str) -> bool:
        """Détecte si le document contient des listes numérotées."""
        # Au moins 3 lignes consécutives avec numérotation
        pattern = r'^(\d+\.|[-*]\s+).*\n(^\d+\.|^[-*]\s+).*\n(^\d+\.|^[-*]\s+)'
        return bool(re.search(pattern, content, re.MULTILINE))

    def _has_table(self, content: str) -> bool:
        """Détecte si le document contient des tableaux."""
        # Tables markdown ou ASCII
        patterns = [
            r'\|.*\|.*\|',  # Tables markdown
            r'\+[-=]+\+',   # Tables ASCII
        ]
        for pattern in patterns:
            if re.search(pattern, content):
                return True
        return False

    def _split_by_sections(self, doc: Document) -> List[Document]:
        """Découpe par sections en préservant la cohérence."""
        content = doc.page_content
        chunks = []

        # Patterns de sections
        section_pattern = r'(^#+\s+.+$|^Article\s+\d+.+$|^Section\s+\d+.+$|^Chapitre\s+\d+.+$|^[IVX]+\.\s+.+$|^\d+\.\s+[A-Z].+$)'

        # Split par sections
        sections = re.split(section_pattern, content, flags=re.MULTILINE | re.IGNORECASE)

        current_chunk = ""
        current_title = ""

        for i, section in enumerate(sections):
            if not section.strip():
                continue

            # Vérifier si c'est un titre de section
            is_title = re.match(section_pattern, section.strip(), re.IGNORECASE)

            if is_title:
                current_title = section.strip()
            else:
                section_content = section.strip()

                # Si ajouter cette section dépasse max_chunk_size, créer un nouveau chunk
                if len(current_chunk) + len(section_content) > self.max_chunk_size and current_chunk:
                    # Sauvegarder le chunk actuel
                    chunk_doc = Document(
                        page_content=current_chunk.strip(),
                        metadata={**doc.metadata, 'section': current_title}
                    )
                    chunks.append(chunk_doc)

                    # Commencer nouveau chunk avec overlap (titre + début section)
                    overlap_text = self._get_overlap(current_chunk, self.chunk_overlap)
                    current_chunk = overlap_text + "\n\n" + current_title + "\n" + section_content
                else:
                    # Ajouter à current_chunk
                    if current_chunk:
                        current_chunk += "\n\n" + current_title + "\n" + section_content
                    else:
                        current_chunk = current_title + "\n" + section_content

                current_title = ""

        # Dernier chunk
        if current_chunk.strip():
            chunk_doc = Document(
                page_content=current_chunk.strip(),
                metadata=doc.metadata
            )
            chunks.append(chunk_doc)

        # Si pas de chunks créés, fallback
        if not chunks:
            return self.fallback_splitter.split_documents([doc])

        return chunks

    def _split_by_lists(self, doc: Document) -> List[Document]:
        """Découpe en préservant les listes complètes."""
        content = doc.page_content
        chunks = []

        # Détecter les blocs de listes
        list_pattern = r'((?:^\d+\.|^[-*]\s+).+(?:\n(?:^\d+\.|^[-*]\s+).+)*)'

        # Split par blocs de liste vs texte normal
        parts = re.split(f'({list_pattern})', content, flags=re.MULTILINE)

        current_chunk = ""

        for part in parts:
            if not part.strip():
                continue

            # Si ajouter ce bloc dépasse max_chunk_size, créer un nouveau chunk
            if len(current_chunk) + len(part) > self.max_chunk_size and current_chunk:
                chunk_doc = Document(
                    page_content=current_chunk.strip(),
                    metadata=doc.metadata
                )
                chunks.append(chunk_doc)

                # Overlap
                overlap_text = self._get_overlap(current_chunk, self.chunk_overlap)
                current_chunk = overlap_text + "\n\n" + part
            else:
                if current_chunk:
                    current_chunk += "\n\n" + part
                else:
                    current_chunk = part

        # Dernier chunk
        if current_chunk.strip():
            chunk_doc = Document(
                page_content=current_chunk.strip(),
                metadata=doc.metadata
            )
            chunks.append(chunk_doc)

        if not chunks:
            return self.fallback_splitter.split_documents([doc])

        return chunks

    def _split_preserve_tables(self, doc: Document) -> List[Document]:
        """Découpe en préservant les tableaux intacts."""
        content = doc.page_content
        chunks = []

        # Pattern de tableau markdown/ASCII
        table_pattern = r'(\|.+\|(?:\n\|.+\|)+|\+[-=]+\+(?:\n.+\n)+\+[-=]+\+)'

        # Split par tableaux
        parts = re.split(f'({table_pattern})', content, flags=re.MULTILINE)

        current_chunk = ""

        for part in parts:
            if not part.strip():
                continue

            # Détecter si c'est un tableau
            is_table = re.search(table_pattern, part)

            if is_table:
                # Toujours garder le tableau intact
                if current_chunk:
                    chunk_doc = Document(
                        page_content=current_chunk.strip(),
                        metadata=doc.metadata
                    )
                    chunks.append(chunk_doc)

                # Tableau comme chunk séparé (même si > max_chunk_size)
                chunk_doc = Document(
                    page_content=part.strip(),
                    metadata={**doc.metadata, 'contains_table': True}
                )
                chunks.append(chunk_doc)
                current_chunk = ""
            else:
                # Texte normal
                if len(current_chunk) + len(part) > self.max_chunk_size and current_chunk:
                    chunk_doc = Document(
                        page_content=current_chunk.strip(),
                        metadata=doc.metadata
                    )
                    chunks.append(chunk_doc)

                    overlap_text = self._get_overlap(current_chunk, self.chunk_overlap)
                    current_chunk = overlap_text + "\n\n" + part
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + part
                    else:
                        current_chunk = part

        # Dernier chunk
        if current_chunk.strip():
            chunk_doc = Document(
                page_content=current_chunk.strip(),
                metadata=doc.metadata
            )
            chunks.append(chunk_doc)

        if not chunks:
            return self.fallback_splitter.split_documents([doc])

        return chunks

    def _get_overlap(self, text: str, overlap_size: int) -> str:
        """Récupère les derniers overlap_size caractères du texte."""
        if len(text) <= overlap_size:
            return text
        return text[-overlap_size:]

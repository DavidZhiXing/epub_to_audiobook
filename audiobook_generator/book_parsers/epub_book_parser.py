import logging
import re
from typing import List, Tuple

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from audiobook_generator.book_parsers.base_book_parser import BaseBookParser
from audiobook_generator.config.general_config import GeneralConfig

logger = logging.getLogger(__name__)


class EpubBookParser(BaseBookParser):
    def __init__(self, config: GeneralConfig):
        super().__init__(config)
        logger.setLevel(config.log)
        self.book = epub.read_epub(self.config.input_file)

    def __str__(self) -> str:
        return super().__str__()

    def validate_config(self):
        if self.config.input_file is None:
            raise ValueError("Epub Parser: Input file cannot be empty")
        if not self.config.input_file.endswith(".epub"):
            raise ValueError(f"Epub Parser: Unsupported file format: {self.config.input_file}")

    def get_book(self):
        return self.book

    def get_book_title(self) -> str:
        if self.book.get_metadata('DC', 'title'):
            return self.book.get_metadata("DC", "title")[0][0]
        return "Untitled"

    def get_book_author(self) -> str:
        if self.book.get_metadata('DC', 'creator'):
            return self.book.get_metadata("DC", "creator")[0][0]
        return "Unknown"
    
    def prep_text(self, text_in):
        # Replace some chars with comma to improve TTS by introducing a pause
        text = (
            text_in.replace("--", ", ")
            .replace("—", ", ")
            .replace(";", ", ")
            .replace(":", ", ")
            .replace("''", ", ")
            .replace("’", "'")
            .replace('“', '"')
            .replace('”', '"')
            .replace("◇", "")
            .replace(" . . . ", ", ")
            .replace("... ", ", ")
            .replace("«", " ")
            .replace("»", " ")
            .replace("[", "")
            .replace("]", "")
            .replace("&", " and ")
            .replace(" GNU ", " new ")
            .replace("\n", " \n")
            .replace("*", " ")
            .strip()
        )
        return text
    
    blacklist = [
        "[document]",
        "noscript",
        "header",
        "html",
        "meta",
        "head", 
        "input",
        "script",
        # Add 'pre' and 'code' to the blacklist
        "pre",
        "code",
    ]
    
    # def chap2text(self, chap):
    #     blacklist = [
    #         "[document]",
    #         "noscript",
    #         "header",
    #         "html",
    #         "meta",
    #         "head",
    #         "input",
    #         "script",
    #     ]
    #     output = ""
    #     soup = BeautifulSoup(chap, "html.parser")
    #     if self.skiplinks:
    #         # Remove everything that is an href
    #         for a in soup.findAll("a", href=True):
    #             a.extract()
    #     # Always skip reading links that are just a number (footnotes)
    #     for a in soup.findAll("a", href=True):
    #         if not any(char.isalpha() for char in a.text):
    #             a.extract()
    #     text = soup.find_all(string=True)
    #     for t in text:
    #         if t.parent.name not in blacklist:
    #             output += "{} ".format(t)
    #     return output

    def get_chapters(self, break_string) -> List[Tuple[str, str]]:
        chapters = []
        for item in self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            content = item.get_content()
            soup = BeautifulSoup(content, "lxml")
            for tag in soup.find_all(self.blacklist):
                tag.decompose()
                
            for a in soup.findAll("a", href=True):
                a.decompose()
            title = ""
            title_levels = ['title', 'h1', 'h2', 'h3']
            for level in title_levels:
                if soup.find(level):
                    title = soup.find(level).text
                    break
            raw = soup.get_text(strip=False)
            logger.debug(f"Raw text: <{raw[:]}>")

            # Replace excessive whitespaces and newline characters based on the mode
            raw = self.prep_text(raw)
            if self.config.newline_mode == "single":
                cleaned_text = re.sub(r"[\n]+", break_string, raw.strip())
            elif self.config.newline_mode == "double":
                cleaned_text = re.sub(r"[\n]{2,}", break_string, raw.strip())
            else:
                raise ValueError(f"Invalid newline mode: {self.config.newline_mode}")

            logger.debug(f"Cleaned text step 1: <{cleaned_text[:]}>")
            cleaned_text = re.sub(r"\s+", " ", cleaned_text)
            logger.debug(f"Cleaned text step 2: <{cleaned_text[:100]}>")

            # Removes end-note numbers
            if self.config.remove_endnotes:
                cleaned_text = re.sub(r'(?<=[a-zA-Z.,!?;”")])\d+', "", cleaned_text)
                logger.debug(f"Cleaned text step 4: <{cleaned_text[:100]}>")
                
            # if text is chinese, remove the space between chinese characters
            if self.config.language.startswith("zh"):
                # 进一步确认是否为汉字句子
                # 首先拆分cleaned_text为句子
                sentences = re.split(r"[。？！]", cleaned_text)
                # 判断句子是否包含汉字，移除句子中的空格
                for sentence in sentences:
                    if re.search(r'[\u4e00-\u9fa5]', sentence):
                        cleaned_sentence = re.sub(r"\s+", "", sentence)
                        cleaned_text = cleaned_text.replace(sentence, cleaned_sentence)
                logger.debug(f"Cleaned text step 5: <{cleaned_text[:100]}>")

            # fill in the title if it's missing
            if title == "":
                title = cleaned_text[:60]
            logger.debug(f"Raw title: <{title}>")
            title = self._sanitize_title(title, break_string)
            logger.debug(f"Sanitized title: <{title}>")

            chapters.append((title, cleaned_text))
            soup.decompose()
        return chapters

    @staticmethod
    def _sanitize_title(title, break_string) -> str:
        # replace MAGIC_BREAK_STRING with a blank space
        # strip incase leading bank is missing
        title = title.replace(break_string, " ")
        sanitized_title = re.sub(r"[^\w\s]", "", title, flags=re.UNICODE)
        sanitized_title = re.sub(r"\s+", "_", sanitized_title.strip())
        return sanitized_title

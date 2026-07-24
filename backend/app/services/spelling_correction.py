import re
from pathlib import Path
from symspellpy import SymSpell, Verbosity
from underthesea import word_tokenize, ner

from app.utils.logger import get_logger

logger = get_logger(__name__)

DICT_DIR = Path(__file__).parent / "dictionary"


class SpellingCorrector:
    def __init__(self):
        self.sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7, count_threshold=1)
        self.sym_spell_2gram = SymSpell(max_dictionary_edit_distance=2, prefix_length=7, count_threshold=1)
        self.sym_spell_3gram = SymSpell(max_dictionary_edit_distance=2, prefix_length=7, count_threshold=1)

        self.sym_spell.load_dictionary(str(DICT_DIR / "frequency_vi_test.txt"), 0, 1, "$", encoding="utf-8")
        self.sym_spell_2gram.load_dictionary(str(DICT_DIR / "dic_2_gram_test.txt"), 0, 1, "$", encoding="utf-8")
        self.sym_spell_3gram.load_dictionary(str(DICT_DIR / "dic_3_gram_test.txt"), 0, 1, "$", encoding="utf-8")
        logger.info("N-gram spelling corrector loaded (%d / %d / %d entries)",
                     self.sym_spell.entry_count,
                     self.sym_spell_2gram.entry_count,
                     self.sym_spell_3gram.entry_count)

    def fix_spelling(self, text: str) -> str:
        tokens = word_tokenize(text, format="text").split()
        suggestions = self._token_suggestions(tokens)

        padded = [None] + suggestions + [None]
        result_tokens = []
        i = 1
        while i < len(padded) - 1:
            s = padded[i]
            if not s or len(s) <= 1:
                t = s[0][0] if s else ""
                result_tokens.append(t)
                i += 1
                continue
            left_word = padded[i - 1][0][0] if padded[i - 1] and padded[i - 1][0][1] != -1 else ""
            if not left_word and i >= 2 and padded[i - 2]:
                left_word = padded[i - 2][0][0]
            max_res, _ = self._best_candidate(s, left_word, padded[i + 1])
            word = max_res[1]
            if max_res[0] == "right":
                result_tokens.append(word)
                i += 2
            else:
                if result_tokens:
                    result_tokens[-1] = word
                else:
                    result_tokens.append(word)
                i += 1

        result = " ".join(t.replace("_", " ") for t in result_tokens).strip()
        result = re.sub(r'\s+([.,!?;:])', r'\1', result)
        return result

    def _token_suggestions(self, tokens: list[str]) -> list[list]:
        result = []
        for word in tokens:
            if not self._is_valid_token(word):
                result.append([[word, 0, -1]])
                continue
            if len(word.split()) == 1:
                suggestions = self.sym_spell.lookup(word.lower(), Verbosity.CLOSEST, max_edit_distance=2)
            else:
                suggestions = self.sym_spell.lookup_compound(word.lower(), 2)
            sug = [[s.term, s.distance, s.count] for s in suggestions]
            if not sug:
                parts = word.replace("_", " ").split()
                for p in parts:
                    psug = self.sym_spell.lookup(p.lower(), Verbosity.CLOSEST, max_edit_distance=2)
                    if psug:
                        result.append([[s.term, s.distance, s.count] for s in psug])
                    else:
                        result.append([[p, 0, 0]])
            else:
                result.append(sug)
        return result

    def _best_candidate(self, suggestion: list, left_word: str, right_suggestions: list) -> tuple:
        best = ["", "", -1]
        sum_count = 0
        for s in suggestion:
            right_corresponds = [f"{s[0].replace(' ', '_')}_{r[0].replace(' ', '_')}" for r in right_suggestions]
            left_correspond = [f"{left_word.replace(' ', '_')}_{s[0].replace(' ', '_')}"]
            tri_correspond = [f"{left_word.replace(' ', '_')}_{r}" for r in right_corresponds]

            left_prob = self._prob_2gram(left_correspond)
            right_prob = self._prob_2gram(right_corresponds)
            tri_prob = self._prob_3gram(tri_correspond)
            sum_count += left_prob[2] + right_prob[2] + tri_prob[2]

            for prob, direction in [(left_prob, "left"), (right_prob, "right"), (tri_prob, "tri")]:
                p = prob[1] / sum_count if sum_count > 0 else 0
                if p > best[2]:
                    best = [direction, prob[0], p]
        return best, sum_count

    def _prob_2gram(self, words: list[str]) -> list:
        best_word = ""
        max_count = -1
        sum_count = 0
        for w in words:
            suggestions = self.sym_spell_2gram.lookup(w, Verbosity.CLOSEST, max_edit_distance=2)
            c = self._exact_count(suggestions)
            sum_count += c
            if c > max_count:
                max_count = c
                best_word = w
        return [best_word, max_count, sum_count]

    def _prob_3gram(self, words: list[str]) -> list:
        best_word = ""
        max_count = -1
        sum_count = 0
        for w in words:
            suggestions = self.sym_spell_3gram.lookup(w, Verbosity.CLOSEST, max_edit_distance=2)
            c = self._exact_count(suggestions)
            sum_count += c
            if c > max_count:
                max_count = c
                best_word = w
        return [best_word, max_count, sum_count]

    @staticmethod
    def _exact_count(suggestions) -> int:
        for s in suggestions:
            if s.distance == 0:
                return s.count
        return 0

    @staticmethod
    def _is_valid_token(token: str) -> bool:
        if re.match(r'^\d+(\.\d+)?$', token):
            return False
        if "_" in token and ner(token.replace("_", " "))[0][1] == "Np":
            return False
        if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", token):
            return False
        if re.match(r"^(0[3|5|7|8|9])([0-9]{8})$", token):
            return False
        return all(c.isalpha() or c == '_' for c in token)


_CORRECTOR = None


def get_spelling_corrector() -> SpellingCorrector:
    global _CORRECTOR
    if _CORRECTOR is None:
        logger.info("Loading n-gram spelling corrector...")
        _CORRECTOR = SpellingCorrector()
    return _CORRECTOR

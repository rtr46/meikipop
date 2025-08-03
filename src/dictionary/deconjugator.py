# deconjugator.py
from dataclasses import dataclass, field
from typing import Set

@dataclass(frozen=True)
class Form:
    text: str
    process: tuple = field(default_factory=tuple)
    tags: tuple = field(default_factory=tuple)

    def __repr__(self):
        return f"Form(text='{self.text}', process={self.process}, tags={self.tags})"

class Deconjugator:
    def __init__(self, rules: list[dict]):
        self.rules = [r for r in rules if isinstance(r, dict)]

    def deconjugate(self, text: str) -> Set[Form]:
        clean_text = text.strip()
        if not clean_text:
            return set()

        processed: Set[Form] = set()
        novel: Set[Form] = {Form(text=clean_text)}

        iteration = 0
        while novel:
            iteration += 1
            if iteration > 15: break

            new_novel: Set[Form] = set()
            for form in novel:
                for rule in self.rules:
                    rule_type = rule.get('type')
                    if not rule_type or rule_type == 'substitution': continue

                    if rule_type == 'onlyfinalrule' and form.tags: continue
                    if rule_type == 'neverfinalrule' and not form.tags: continue

                    new_forms = self._apply_rule(form, rule)
                    if new_forms:
                        for f in new_forms:
                            if f not in processed and f not in novel and f not in new_novel:
                                new_novel.add(f)

            processed.update(novel)
            novel = new_novel

        processed.add(Form(text=clean_text))
        return processed

    def _apply_rule(self, form: Form, rule: dict) -> Set[Form] | None:
        if 'dec_end' not in rule or 'con_end' not in rule:
            return None

        dec_ends = rule['dec_end'] if isinstance(rule['dec_end'], list) else [rule['dec_end']]
        con_ends = rule['con_end'] if isinstance(rule['con_end'], list) else [rule['con_end']]

        con_tags_from_rule = rule.get('con_tag')
        dec_tags_from_rule = rule.get('dec_tag')

        con_tags = [con_tags_from_rule] if con_tags_from_rule and not isinstance(con_tags_from_rule,
                                                                                 list) else con_tags_from_rule
        dec_tags = [dec_tags_from_rule] if dec_tags_from_rule and not isinstance(dec_tags_from_rule,
                                                                                 list) else dec_tags_from_rule

        max_len = 1
        list_source = next((lst for lst in [dec_ends, con_ends, dec_tags, con_tags] if isinstance(lst, list)), None)
        if list_source: max_len = len(list_source)

        results = set()

        for i in range(max_len):
            con_end = con_ends[i % len(con_ends)] if con_ends else ""
            con_tag = con_tags[i % len(con_tags)] if con_tags else None
            dec_end = dec_ends[i % len(dec_ends)] if dec_ends else ""
            dec_tag = dec_tags[i % len(dec_tags)] if dec_tags else None

            suffix_match = form.text.endswith(con_end)

            current_form_tag = form.tags[-1] if form.tags else None
            tag_match = False
            is_starter_type = rule.get('type') in ['stdrule', 'rewriterule', 'onlyfinalrule', 'contextrule']

            if not form.tags and is_starter_type:
                tag_match = True
            elif form.tags:
                tag_match = (current_form_tag == con_tag)

            if not suffix_match or not tag_match:
                continue

            if rule.get('type') == 'rewriterule' and form.text != con_end:
                continue

            new_text = form.text[:-len(con_end)] + dec_end if con_end else form.text + dec_end
            new_process = form.process + (rule.get('detail', ''),)

            if form.tags:
                new_tags = form.tags[:-1] + (dec_tag,) if dec_tag is not None else form.tags[:-1]
            else:
                new_tags = (dec_tag,) if dec_tag is not None else ()

            new_form_to_add = Form(text=new_text, process=new_process, tags=new_tags)
            results.add(new_form_to_add)

        return results if results else None
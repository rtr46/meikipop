# deconjugator.py
from dataclasses import dataclass, field
from typing import Set

@dataclass(frozen=True)
class Form:
    """Represents a potential deconjugated form of a word."""
    text: str
    process: tuple = field(default_factory=tuple)
    tags: tuple = field(default_factory=tuple)

    def __repr__(self):
        return f"Form(text='{self.text}', process={self.process}, tags={self.tags})"

class Deconjugator:
    """
    Finds all possible dictionary forms of a given conjugated word.
    """
    def __init__(self, rules: list[dict]):
        self.rules = rules

    def deconjugate(self, text: str) -> Set[Form]:
        clean_text = text.strip()
        if not clean_text:
            return set()

        processed: Set[Form] = set()
        novel: Set[Form] = {Form(text=clean_text)}
        
        iteration = 0
        while novel:
            iteration += 1
            if iteration > 15:
                break
            
            new_novel: Set[Form] = set()
            for form in novel:
                for rule in self.rules:
                    rule_type = rule.get('type')
                    if not rule_type: continue

                    if rule_type == 'onlyfinalrule' and form.tags:
                        continue
                    if rule_type == 'neverfinalrule' and not form.tags:
                        continue
                    
                    new_forms = self._apply_rule(form, rule)
                    if new_forms:
                        for f in new_forms:
                            if f not in processed and f not in novel and f not in new_novel:
                                new_novel.add(f)
            
            processed.update(novel)
            novel = new_novel
        
        return processed

    def _apply_rule(self, form: Form, rule: dict) -> Set[Form] | None:
        if 'dec_end' not in rule or 'con_end' not in rule:
            return None
            
        dec_ends = rule['dec_end'] if isinstance(rule['dec_end'], list) else [rule['dec_end']]
        con_ends = rule['con_end'] if isinstance(rule['con_end'], list) else [rule['con_end']]
        dec_tags = rule.get('dec_tag')
        con_tags = rule.get('con_tag')

        dec_tags = dec_tags if isinstance(dec_tags, list) else [dec_tags]
        con_tags = con_tags if isinstance(con_tags, list) else [con_tags]

        max_len = max(len(dec_ends), len(con_ends), len(dec_tags), len(con_tags))
        results = set()

        for i in range(max_len):
            con_end = con_ends[i % len(con_ends)]
            con_tag = con_tags[i % len(con_tags)]
            
            if not form.text.endswith(con_end):
                continue
            
            current_form_tag = form.tags[-1] if form.tags else None
            
            is_starter_rule = rule.get('type') in ['stdrule', 'rewriterule']
            if form.tags and not is_starter_rule and current_form_tag != con_tag:
                continue
            if form.tags and is_starter_rule and current_form_tag != con_tag:
                continue

            dec_end = dec_ends[i % len(dec_ends)]
            dec_tag = dec_tags[i % len(dec_tags)]

            if rule.get('type') == 'rewriterule' and form.text != con_end:
                continue

            new_text = form.text[:-len(con_end)] + dec_end if con_end else form.text + dec_end
            new_process = form.process + (rule.get('detail', ''),)
            
            if form.tags:
                new_tags = form.tags[:-1] + (dec_tag,)
            else:
                new_tags = (dec_tag,)
            
            if dec_tag is not None:
                results.add(Form(text=new_text, process=new_process, tags=new_tags))
            
        return results if results else None
import re
from typing import Dict, Tuple, List
from isa import Comment, Macros, Label


class Preprocessor:
    def __init__(self) -> None:
        self.defines: Dict[str, str] = dict()
        self.macros: Dict[str, Tuple[List[str], str]] = dict()
        self.macro_counter: int = 0

    def _remove_comments(self, source: str) -> str:
        return Comment.regex.sub("", source)

    def _evaluate_condition(self, condition: str) -> bool:
        condition = condition.strip()
        if "==" in condition:
            parts = condition.split("==")
            left = self.defines.get(parts[0].strip(), parts[0].strip())
            right = self.defines.get(parts[1].strip(), parts[1].strip())
            return left == right

        val = self.defines.get(condition, None)
        if val is None:
            return False
        return val.lower() not in ("0", "false", "no")

    def _replace_conditional(self, match: re.Match[str]) -> str:
        groups = match.groups()
        if self._evaluate_condition(groups[0]):
            return groups[1]
        if groups[2] and self._evaluate_condition(groups[2]):
            return groups[3]
        if groups[4]:
            return groups[4]
        return ""

    def _process_conditionals(self, source: str) -> str:
        while "@if" in source:
            source = Macros.if_regex.sub(self._replace_conditional, source)
        return source

    def _save_macro(self, match: re.Match[str]) -> str:
        name = match.group(1)
        params = [p.strip() for p in match.group(2).split(",") if p.strip()]
        body = match.group(3)
        self.macros[name] = (params, body)
        return ""

    def _collect_directives(self, source: str) -> str:
        lines: List[str] = list()
        for line in source.splitlines():
            match = Macros.def_regex.match(line.strip())
            if match:
                self.defines[match.group(1)] = match.group(2).strip()
            else:
                lines.append(line)
        return Macros.macro_regex.sub(self._save_macro, "\n".join(lines))

    def _expand_macros_and_defines(self, source: str) -> str:
        expanded = True
        while expanded:
            expanded = False
            for name, (params, body) in self.macros.items():
                call_pattern = re.compile(rf"\${name}\s*\((.*?)\)")

                def replace_macro(match: re.Match[str]):
                    self.macro_counter += 1
                    args = [a.strip() for a in match.group(1).split(",") if a.strip()]

                    local_body = body
                    local_labels = set(re.findall(rf"({Label.pattern}):", local_body))
                    for label in local_labels:
                        local_body = re.sub(
                            rf"\b{label}\b", f"{label}_{self.macro_counter}", local_body
                        )

                    for param, arg in zip(params, args):
                        local_body = local_body.replace(f"%{param}", arg)
                    return local_body

                if call_pattern.search(source):
                    source = call_pattern.sub(replace_macro, source)
                    expanded = True

            for key in sorted(self.defines.keys(), key=len, reverse=True):
                key_pattern = re.compile(rf"\${key}\b")
                if key_pattern.search(source):
                    source = key_pattern.sub(self.defines[key], source)
                    expanded = True
        return source

    def preprocess(self, source: str) -> str:
        source = self._remove_comments(source)
        source = self._collect_directives(source)
        source = self._process_conditionals(source)
        source = self._expand_macros_and_defines(source)
        return "\n".join([line for line in source.splitlines() if line.strip()])

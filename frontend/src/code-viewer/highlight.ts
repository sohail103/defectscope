import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import c from "highlight.js/lib/languages/c";
import cpp from "highlight.js/lib/languages/cpp";

hljs.registerLanguage("python", python);
hljs.registerLanguage("c", c);
hljs.registerLanguage("cpp", cpp);

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** Highlight a whole file once, then split into per-line HTML, re-opening spans that cross line breaks. */
export function highlightLines(code: string, language?: string | null): string[] {
  if (!language || !hljs.getLanguage(language)) return code.split("\n").map(esc);
  const html = hljs.highlight(code, { language, ignoreIllegals: true }).value;
  const lines: string[] = [];
  const stack: string[] = [];
  let cur = "";
  let last = 0;
  const re = /(<span[^>]*>|<\/span>|\n)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    cur += html.slice(last, m.index);
    last = m.index + m[0].length;
    if (m[0] === "\n") { cur += "</span>".repeat(stack.length); lines.push(cur); cur = stack.join(""); }
    else if (m[0] === "</span>") { stack.pop(); cur += m[0]; }
    else { stack.push(m[0]); cur += m[0]; }
  }
  cur += html.slice(last) + "</span>".repeat(stack.length);
  lines.push(cur);
  return lines;
}

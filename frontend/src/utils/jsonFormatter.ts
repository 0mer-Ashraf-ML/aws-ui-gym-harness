const HIGHLIGHT_REGEX =
  /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g;

const escapeHtml = (unsafe: string) =>
  unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

export const formatJsonWithSyntaxHighlighting = (value: unknown): string => {
  let jsonString: string;

  if (typeof value === "string") {
    try {
      jsonString = JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      jsonString = value;
    }
  } else {
    try {
      jsonString = JSON.stringify(value, null, 2);
    } catch {
      jsonString = String(value ?? "");
    }
  }

  return escapeHtml(jsonString).replace(HIGHLIGHT_REGEX, (match) => {
    let cls = "json-number";
    if (/^"/.test(match)) {
      if (/:$/.test(match)) {
        cls = "json-key";
      } else {
        cls = "json-string";
      }
    } else if (/true|false/.test(match)) {
      cls = "json-boolean";
    } else if (/null/.test(match)) {
      cls = "json-null";
    }
    return `<span class="${cls}">${match}</span>`;
  });
};


use regex::Regex;
use scraper::{ElementRef, Html, Selector};
use std::sync::OnceLock;

fn script_re() -> &'static Regex {
    static SCRIPT_RE: OnceLock<Regex> = OnceLock::new();
    SCRIPT_RE.get_or_init(|| {
        Regex::new(r"(?is)<script[^>]*>.*?</script>").expect("valid script regex")
    })
}

fn style_re() -> &'static Regex {
    static STYLE_RE: OnceLock<Regex> = OnceLock::new();
    STYLE_RE.get_or_init(|| {
        Regex::new(r"(?is)<style[^>]*>.*?</style>").expect("valid style regex")
    })
}

/// Tags whose subtrees are printed with locator + text information.
const INTERACTIVE_TAGS: &[&str] = &[
    "a", "button", "input", "select", "textarea", "label", "option",
];

/// Tags that create indentation context (layout / grouping elements).
const STRUCTURAL_TAGS: &[&str] = &[
    "form", "nav", "main", "dialog", "table", "tr", "td", "th",
    "section", "aside",
];

/// Tags whose entire subtree is discarded.
const SKIP_TAGS: &[&str] = &[
    "header", "footer", "script", "style", "head", "noscript",
    "svg", "meta", "link",
];

/// Attributes kept in the serialized output.
const KEEP_ATTRS: &[&str] = &[
    "id",
    "name",
    "role",
    "type",
    "href",
    "src",
    "action",
    "method",
    "placeholder",
    "value",
    "for",
    "aria-label",
    "aria-expanded",
    "aria-checked",
    "aria-disabled",
    "aria-labelledby",
    "data-testid",
    "data-pw",
    "data-id",
];

/// Anonymous containers are kept only when they carry one of these.
const IDENTITY_ATTRS: &[&str] = &["id", "role", "aria-label", "data-testid"];

const TEXT_MAX_CHARS: usize = 100;

fn truncate_chars(s: &str, max: usize) -> &str {
    match s.char_indices().nth(max) {
        Some((i, _)) => &s[..i],
        None => s,
    }
}

fn serialize_element(el: ElementRef, depth: usize, out: &mut String) {
    let tag = el.value().name();

    // Discard entire subtree for skip tags.
    if SKIP_TAGS.iter().any(|&s| s == tag) {
        return;
    }

    let is_interactive = INTERACTIVE_TAGS.iter().any(|&s| s == tag);
    let is_structural = STRUCTURAL_TAGS.iter().any(|&s| s == tag);
    let has_identity = IDENTITY_ATTRS
        .iter()
        .any(|&attr| el.value().attr(attr).is_some());

    let emit = is_interactive || is_structural || has_identity;

    if emit {
        let indent = "  ".repeat(depth);

        // id shown as tag#id shorthand.
        let id_suffix = el
            .value()
            .attr("id")
            .map(|v| format!("#{}", v))
            .unwrap_or_default();

        // Remaining kept attributes in [key=value] order.
        let attr_str: String = KEEP_ATTRS
            .iter()
            .filter(|&&k| k != "id")
            .filter_map(|&k| {
                el.value()
                    .attr(k)
                    .map(|v| format!("[{}={}]", k, v))
            })
            .collect();

        // Direct text nodes only (not deep descendants), joined and truncated.
        let direct_text: String = el
            .children()
            .filter_map(|node| {
                node.value()
                    .as_text()
                    .map(|t| t.to_string())
            })
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(" ");

        let text_str = if !direct_text.is_empty() {
            format!(" \"{}\"", truncate_chars(&direct_text, TEXT_MAX_CHARS))
        } else {
            String::new()
        };

        out.push_str(&format!(
            "{}{}{}{}{}\n",
            indent, tag, id_suffix, attr_str, text_str
        ));
    }

    // Recurse into children. Depth increases only when we emitted this element.
    let next_depth = if emit { depth + 1 } else { depth };
    for child in el.children() {
        if let Some(child_el) = ElementRef::wrap(child) {
            serialize_element(child_el, next_depth, out);
        }
    }
}

pub fn reduce_html(input: &str) -> String {
    // Keep existing script/style removal.
    let no_script = script_re().replace_all(input, "");
    let no_style = style_re().replace_all(&no_script, "");

    let document = Html::parse_document(&no_style);

    // Start from <body> so <head> is naturally skipped.
    let body_sel = Selector::parse("body").expect("valid selector");
    let mut output = String::new();

    let start_children: Vec<_> = match document.select(&body_sel).next() {
        Some(body) => body.children().collect(),
        None => document.root_element().children().collect(),
    };

    for node in start_children {
        if let Some(el) = ElementRef::wrap(node) {
            serialize_element(el, 0, &mut output);
        }
    }

    output.trim().to_string()
}

#[cfg(test)]
mod tests {
    use super::reduce_html;

    #[test]
    fn produces_semantic_format_without_header_footer() {
        let html = r#"<html><head><title>Test</title></head><body>
            <header><h1>Site</h1></header>
            <main>
                <form id="login" action="/auth">
                    <input name="email" type="email" placeholder="Email address">
                    <button type="submit">Sign In</button>
                    <a href="/forgot">Forgot password?</a>
                </form>
            </main>
            <footer>copyright</footer>
        </body></html>"#;

        let result = reduce_html(html);
        assert!(result.contains("form#login"), "form id shorthand missing");
        assert!(result.contains("[action=/auth]"), "form action missing");
        assert!(result.contains("[name=email]"), "input name missing");
        assert!(result.contains("\"Sign In\""), "button text missing");
        assert!(result.contains("[href=/forgot]"), "link href missing");
        assert!(!result.contains("Site"), "header should be stripped");
        assert!(!result.contains("copyright"), "footer should be stripped");
    }

    #[test]
    fn nav_links_are_preserved() {
        let html = r#"<body>
            <nav role="navigation">
                <a href="/home">Home</a>
                <a href="/dashboard">Dashboard</a>
            </nav>
        </body>"#;

        let result = reduce_html(html);
        assert!(result.contains("nav[role=navigation]"));
        assert!(result.contains("[href=/home]"));
        assert!(result.contains("\"Home\""));
        assert!(result.contains("[href=/dashboard]"));
    }

    #[test]
    fn script_and_style_blocks_removed() {
        let html = r#"<body>
            <script>doSomething()</script>
            <style>.cls { color: red }</style>
            <main><button>OK</button></main>
        </body>"#;

        let result = reduce_html(html);
        assert!(!result.contains("doSomething"));
        assert!(!result.contains("color: red"));
        assert!(result.contains("button"));
    }
}

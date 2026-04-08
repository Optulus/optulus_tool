use regex::Regex;
use std::sync::OnceLock;

fn script_re() -> &'static Regex {
    static SCRIPT_RE: OnceLock<Regex> = OnceLock::new();
    SCRIPT_RE.get_or_init(|| {
        Regex::new(r"(?is)<script[^>]*>.*?</script>").expect("valid script regex")
    })
}

fn style_re() -> &'static Regex {
    static STYLE_RE: OnceLock<Regex> = OnceLock::new();
    STYLE_RE
        .get_or_init(|| Regex::new(r"(?is)<style[^>]*>.*?</style>").expect("valid style regex"))
}

fn tag_re() -> &'static Regex {
    static TAG_RE: OnceLock<Regex> = OnceLock::new();
    TAG_RE.get_or_init(|| Regex::new(r"(?is)<[^>]+>").expect("valid tag regex"))
}

fn whitespace_re() -> &'static Regex {
    static WHITESPACE_RE: OnceLock<Regex> = OnceLock::new();
    WHITESPACE_RE.get_or_init(|| Regex::new(r"\s+").expect("valid whitespace regex"))
}

pub fn reduce_html(input: &str) -> String {
    let no_script = script_re().replace_all(input, " ");
    let no_style = style_re().replace_all(&no_script, " ");
    let without_tags = tag_re().replace_all(&no_style, " ");
    whitespace_re().replace_all(&without_tags, " ").trim().to_string()
}

#[cfg(test)]
mod tests {
    use super::reduce_html;

    #[test]
    fn strips_tags_and_scripts() {
        let html = "<html><script>noise</script><body><h1>Hello</h1><p>World</p></body></html>";
        let reduced = reduce_html(html);
        assert_eq!(reduced, "Hello World");
    }
}

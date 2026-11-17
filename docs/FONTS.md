# Shop theme fonts (S14)

The six shop themes use self-hosted, open-licensed fonts. Nothing is loaded from Google Fonts or any other outside
host: the pages ask the app itself for `/shop-assets/fonts/<name>.woff2` (cached for a week, the same on a shop's own
address and in the owner's preview), and the page's Content-Security-Policy only allows fonts from its own address.

All fonts are under the **SIL Open Font License 1.1** (full text per family in `docs/fonts/OFL-*.txt`). The licence
allows use, subsetting, modifying (we narrowed variable axes) and embedding on websites, as long as the font is not
sold on its own and the copyright / licence stays with it (the licence name and copyright strings are kept inside each
woff2 file, and the text is here). Sources: the Google Fonts repository, https://github.com/google/fonts/tree/main/ofl.

Each file is cut down to Basic Latin, Latin-1, common punctuation, arrows and the rupee sign (U+20B9), without
hinting; variable fonts are pinned to one optical size and the weight range the pages use.
Rebuild with `scripts/build_theme_fonts.py` (needs `fonttools` + `brotli`; the TTFs come from the repository above).
A test (`tests/test_s14_themes.py`) checks every file has the ₹ glyph, that each theme's fonts total at most 120 KB,
and that every file named below is listed here.

| Theme | Headings | Text | Files | Size | Licence file |
|---|---|---|---|---|---|
| Bakery & desserts | Fraunces (SOFT 100, WONK 1, wght 500–800) | DM Sans (400–700) | `fraunces.woff2`, `dm-sans.woff2` | ~51 KB | `OFL-fraunces.txt`, `OFL-dmsans.txt` |
| Home kitchen | Bricolage Grotesque (wght 500–800) | Figtree (400–800) | `bricolage.woff2`, `figtree.woff2` | ~49 KB | `OFL-bricolagegrotesque.txt`, `OFL-figtree.txt` |
| Handmade & crafts | Instrument Serif (regular + italic) | Manrope (400–700) | `instrument-serif.woff2`, `instrument-serif-italic.woff2`, `manrope.woff2` | ~48 KB | `OFL-instrumentserif.txt`, `OFL-manrope.txt` |
| Tailoring & custom | Source Serif 4 (opsz 36, wght 400–700) | Plus Jakarta Sans (400–700) | `source-serif.woff2`, `jakarta.woff2` | ~52 KB | `OFL-sourceserif4.txt`, `OFL-plusjakartasans.txt` |
| Gifts & hampers | Playfair Display (wght 500–800) | Figtree | `playfair.woff2`, `figtree.woff2` | ~50 KB | `OFL-playfairdisplay.txt`, `OFL-figtree.txt` |
| General | Newsreader (opsz 36, wght 400–700) | Manrope (400–700) | `newsreader.woff2`, `manrope.woff2` | ~58 KB | `OFL-newsreader.txt`, `OFL-manrope.txt` |

The rupee sign: every font that sets a price has the ₹ glyph (checked by a test). Instrument Serif (Handmade headlines)
doesn't, so prices on that theme are always set in its text font, Manrope; the headlines never contain a price.
(DM Serif Display, Hanken Grotesk and Lora were tried and dropped for the same reason.)

Fallbacks if a font file can't load: a serif or sans-serif system font (the page stays readable; text swaps in when the
font arrives). Devanagari and other scripts fall back to the visitor's system fonts, as before.

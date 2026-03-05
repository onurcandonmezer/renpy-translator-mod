# Ren'Py Universal Translator Mod

A single-file translation mod that adds real-time dialogue translation to **any** Ren'Py visual novel. Powered by Google Gemini, DeepL, or OpenAI APIs.

## Features

- **Universal compatibility** — Works with Ren'Py 6.x, 7.x, and 8.x
- **Single file installation** — Just drop one `.rpy` file into the game folder
- **3 API providers** — Google Gemini (free tier), DeepL, and OpenAI (GPT-4o-mini)
- **28 languages** supported (Arabic, Chinese, English, French, German, Japanese, Korean, Spanish, Turkish, and more)
- **Two display modes:**
  - **Overlay mode** — Translation appears in a separate panel below dialogue
  - **Inline mode** — Replaces the original dialogue text directly in the textbox
- **Auto-translate mode** — Automatically translates every dialogue line as it appears
- **Translation cache** — Previously translated lines load instantly without API calls (persists across sessions)
- **Word saving** — Right-click translated words to save them for vocabulary building
- **Phrase selection** — Select multiple words to save entire phrases
- **Text-to-Speech** — Listen to pronunciation of saved English words (via Google Translate TTS)
- **XLSX export** — Export saved words to Excel spreadsheet (zero external dependencies)
- **Keyboard shortcuts** — `T` to translate, `Shift+T` to toggle auto-translate
- **In-game settings panel** — Configure everything without leaving the game
- **Adjustable inline font size** — Customize translated text size in inline mode
- **Smart cache management** — Auto-pruning when cache exceeds 5,000 entries

## Installation

1. Download `translator_mod.rpy`
2. Copy it into the `game/` folder of any Ren'Py visual novel
3. Launch the game — you'll see a gear icon in the top-right corner

That's it. No other files or dependencies needed.

## Getting an API Key

This mod supports three translation providers:

### Google Gemini (Free)
1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Copy the generated key

### DeepL
1. Sign up at [deepl.com/pro](https://www.deepl.com/pro#developer) (free tier available)
2. Go to your account's API keys section
3. Copy your Authentication Key

### OpenAI
1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Create a new API key
3. Copy the generated key

## Setup (First Time)

1. In the game, click the **gear icon** (top-right corner) to open settings
2. Select your **API provider** (Gemini, DeepL, or OpenAI)
3. Click **"Paste"** next to the API key field (copies from your clipboard)
4. Select your **target language** from the list
5. Close the settings panel

## Usage

### Manual Translation
- When dialogue appears, click the **"TR"** button (bottom-right) to translate the current line
- Click **"TR"** again to hide the translation
- Or press **T** on your keyboard

### Auto-Translation
- Press **Shift+T** on your keyboard to toggle auto-translate mode
- When enabled, every new dialogue line is automatically translated

### Display Modes
- **Overlay (Panel):** Translation appears in a dark panel above the dialogue box
- **Inline (Replace Text):** Translation replaces the original text directly in the game's dialogue textbox. Supports adjustable font size.

### Reset Button
- Click the **↻** button to reset the translation state if anything gets stuck

### Saving Words
1. After translating a line, **right-click** any word in the translated text
2. Click additional words to select a phrase
3. Click **"Save"** to save the word/phrase — the mod automatically finds the original English equivalent
4. Saved words appear highlighted in green in future translations

### Managing Saved Words
- View saved words in **Settings > Saved Words** tab
- Click the **play button** to hear pronunciation (TTS)
- Delete individual words or clear all
- **Export to XLSX** — saves a `saved_words.xlsx` file to the game directory

## Supported Languages

Arabic, Bengali, Chinese (Simplified), Chinese (Traditional), Czech, Dutch, English, Filipino, French, German, Greek, Hindi, Hungarian, Indonesian, Italian, Japanese, Korean, Malay, Polish, Portuguese (Brazilian), Romanian, Russian, Spanish, Swedish, Thai, Turkish, Ukrainian, Vietnamese

## How It Works

The mod hooks into Ren'Py's dialogue system by wrapping the internal `display_say` function. This approach captures the speaker name and dialogue text regardless of the Ren'Py version, since `display_say(who, what, ...)` has maintained a stable function signature across all versions.

**Translation flow:**
1. The mod intercepts dialogue via the monkey-patched `display_say`
2. Checks the local cache first (`target_lang::stripped_text` as key)
3. If not cached, sends text to the selected API provider in a background thread
4. Translation appears without blocking gameplay
5. Result is cached for future use

**Inline mode** uses a three-layer approach for reliability:
- `display_say` patch replaces `what` parameter for cached translations
- `interact_callbacks` modifies say screen scope before screen evaluation
- Overlay screen's `inline_update` as a fallback to ensure widget text matches

## Settings

| Setting | Description |
|---------|-------------|
| **Mod Status** | Enable/disable the entire mod |
| **Translation Mode** | Switch between Overlay (panel) and Inline (replace text) |
| **Inline Font Size** | Adjust font size for inline translations (Auto or 10-40) |
| **API Provider** | Choose between Gemini, DeepL, or OpenAI |
| **API Key** | Your API key for the selected provider (paste from clipboard) |
| **Target Language** | The language to translate dialogue into |
| **Cache** | View count and clear cached translations |
| **Auto-Translate** | Toggle automatic translation of every line |

## Notes

- The mod uses the `DejaVuSans.ttf` font which is included with all Ren'Py distributions
- Translation cache persists across game sessions via Ren'Py's persistent data
- The "Paste" button uses PowerShell clipboard access (Windows). On other platforms, manually set the API key via the Ren'Py console
- The free Gemini API tier has rate limits. If you see "Too many requests", wait a moment and try again
- Cache is automatically pruned when it exceeds 5,000 entries (removes oldest 20%)
- TTS audio files are cached in `game/tts_cache/` for offline replay

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No buttons visible | Make sure `translator_mod.rpy` is in the `game/` folder, not a subfolder |
| "API key required" | Open settings and paste your API key for the selected provider |
| "Invalid API key" | Your API key may be expired or incorrect. Generate a new one |
| "Too many requests" | You've hit the API rate limit. Wait 30-60 seconds |
| Buttons don't appear during dialogue | Click the ↻ reset button, or restart the game |
| Inline mode shows original text briefly | This is expected for uncached translations — enable auto-translate for best results |
| DeepL language not supported | DeepL supports fewer languages than Gemini — switch provider if needed |

## License

MIT License — See [LICENSE](LICENSE) for details.

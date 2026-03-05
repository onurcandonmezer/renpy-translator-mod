## Universal Translation Mod for Ren'Py
## Drop this single file into any Ren'Py game's "game/" folder.
## Provides on-demand dialogue translation via Google Gemini API.
## Compatible with Ren'Py 6.x, 7.x, and 8.x.

################################################################################
## 1. PERSISTENT DEFAULTS & LANGUAGE LIST (init -100)
################################################################################

init -100 python:

    if persistent._translator_api_key is None:
        persistent._translator_api_key = ""

    if persistent._translator_target_lang is None:
        persistent._translator_target_lang = "English"

    if persistent._translator_cache is None:
        persistent._translator_cache = {}

    # Clean up bad cache entries (punctuation-only keys like "....")
    import re as _tl_re_init
    _tl_bad_keys = [k for k in persistent._translator_cache
                    if "::" in k and not _tl_re_init.sub(r'[^a-zA-ZÀ-ÿ\u0100-\u024F]', '', k.split("::", 1)[1])]
    for _tl_bk in _tl_bad_keys:
        del persistent._translator_cache[_tl_bk]

    if persistent._translator_enabled is None:
        persistent._translator_enabled = True

    if persistent._translator_saved_words is None:
        persistent._translator_saved_words = []

    if persistent._translator_auto_translate is None:
        persistent._translator_auto_translate = False

    if persistent._translator_inline_mode is None:
        persistent._translator_inline_mode = False

    if persistent._translator_inline_font_size is None:
        persistent._translator_inline_font_size = 0  # 0 = auto (use game default)

    if persistent._translator_api_provider is None:
        persistent._translator_api_provider = "gemini"  # "gemini", "deepl", "openai"

    if persistent._translator_deepl_key is None:
        persistent._translator_deepl_key = ""

    if persistent._translator_openai_key is None:
        persistent._translator_openai_key = ""

    _translator_languages = [
        "Arabic", "Bengali", "Chinese (Simplified)", "Chinese (Traditional)",
        "Czech", "Dutch", "English", "Filipino", "French", "German",
        "Greek", "Hindi", "Hungarian", "Indonesian", "Italian", "Japanese",
        "Korean", "Malay", "Polish", "Portuguese (Brazilian)", "Romanian",
        "Russian", "Spanish", "Swedish", "Thai", "Turkish", "Ukrainian",
        "Vietnamese"
    ]

    _translator_deepl_lang_codes = {
        "Arabic": "AR", "Bulgarian": "BG", "Czech": "CS", "Dutch": "NL",
        "English": "EN", "French": "FR", "German": "DE", "Greek": "EL",
        "Hungarian": "HU", "Indonesian": "ID", "Italian": "IT", "Japanese": "JA",
        "Korean": "KO", "Polish": "PL", "Portuguese (Brazilian)": "PT-BR",
        "Romanian": "RO", "Russian": "RU", "Spanish": "ES", "Swedish": "SV",
        "Turkish": "TR", "Ukrainian": "UK", "Chinese (Simplified)": "ZH-HANS",
        "Chinese (Traditional)": "ZH-HANT"
    }

    # Cache pruning at startup
    if persistent._translator_cache and len(persistent._translator_cache) > 5000:
        keys = list(persistent._translator_cache.keys())
        to_remove = keys[:len(keys) // 5]
        for k in to_remove:
            del persistent._translator_cache[k]

################################################################################
## 2. RUNTIME DEFAULTS (rollback-safe)
################################################################################

default _tl_current_what = ""
default _tl_current_who = ""
default _tl_translated_text = ""
default _tl_show_translation = False
default _tl_is_translating = False
default _tl_error_message = ""
default _tl_settings_visible = False
default _tl_settings_tab = "settings"
default _tl_translation_counter = 0
default _tl_saving_word = ""
default _tl_word_select_mode = False
default _tl_selected_indices = []
default _tl_auto_pending = False
default _tl_inline_applied = False
default _tl_inline_text = ""
default _tl_inline_word_popup = ""
default _tl_inline_word_popup_y = 0.5

################################################################################
## 3. FUNCTIONS & HOOKS (init 100)
################################################################################

init 100 python:
    import threading
    import json as _tl_json
    def _tl_log(msg):
            pass

    ##########################################################################
    ## 3a. Text tag stripping utility
    ##########################################################################

    def _translator_strip_tags(text):
        """Remove Ren'Py text tags like {b}, {i}, {color=#fff}, {/b} etc."""
        if not text:
            return ""
        import re
        return re.sub(r'\{[^}]*\}', '', text)

    def _translator_needs_translation(text):
        """Check if text has actual translatable content (not just punctuation/symbols/whitespace)."""
        import re
        cleaned = _translator_strip_tags(text)
        # Remove punctuation, symbols, whitespace, numbers — if nothing left, no translation needed
        letters_only = re.sub(r'[^a-zA-ZÀ-ÿ\u0100-\u024F\u0400-\u04FF\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', '', cleaned)
        return len(letters_only) > 0

    ##########################################################################
    ## 3b. Character callback — cleans up state when dialogue ends
    ##########################################################################

    def _translator_character_callback(event, interact=True, **kwargs):
        if not persistent._translator_enabled:
            return

        if event == "end" and interact:
            store._tl_current_what = ""
            store._tl_current_who = ""
            store._tl_show_translation = False
            store._tl_translated_text = ""
            store._tl_error_message = ""
            store._tl_inline_text = ""
            store._tl_word_select_mode = False
            store._tl_selected_indices = []
            store._tl_inline_word_popup = ""
            store._tl_inline_applied = False

    if _translator_character_callback not in config.all_character_callbacks:
        config.all_character_callbacks.append(_translator_character_callback)

    ##########################################################################
    ## 3c. Register overlay screen
    ##########################################################################

    if "_translator_overlay" not in config.overlay_screens:
        config.overlay_screens.append("_translator_overlay")

    ##########################################################################
    ## 3d. Monkey-patch display_say for universal who/what capture
    ##     Works across all Ren'Py versions (6.x, 7.x, 8.x) since
    ##     display_say(who, what, ...) has a stable function signature.
    ##########################################################################

    import renpy.character as _tl_char_module
    _tl_original_display_say = _tl_char_module.display_say

    def _tl_patched_display_say(who, what, *args, **kwargs):
        _tl_log("=== display_say CALLED === who={}, what={}".format(repr(who), repr(what[:80] if what else None)))
        _tl_log("  enabled={}, inline={}, auto={}".format(
            persistent._translator_enabled, persistent._translator_inline_mode, persistent._translator_auto_translate))
        if persistent._translator_enabled:
            store._tl_current_what = what or ""
            store._tl_current_who = who or ""
            store._tl_show_translation = False
            store._tl_translated_text = ""
            store._tl_error_message = ""
            store._tl_word_select_mode = False
            store._tl_selected_indices = []
            store._tl_inline_applied = False

            # Inline mode: use cached translation directly
            # so original text never appears on screen (no flash)
            if persistent._translator_inline_mode and what:
                stripped = _translator_strip_tags(what)
                target_lang = persistent._translator_target_lang or "English"
                cache_key = "{}::{}".format(target_lang, stripped)
                _tl_log("  cache_key={}".format(repr(cache_key[:80])))
                _tl_log("  cache has key={}".format(
                    bool(persistent._translator_cache and cache_key in persistent._translator_cache)))
                if persistent._translator_cache and cache_key in persistent._translator_cache and _translator_needs_translation(what):
                    cached = persistent._translator_cache[cache_key]
                    store._tl_translated_text = cached
                    store._tl_show_translation = True
                    # Pass plain translated text — no font/size tags
                    # Tags can cause issues with DialogueTextTags and screen processing
                    # Font/size is handled by the overlay screen's inline_update instead
                    what = cached
                    # Force display_say to recreate DialogueTextTags from our modified what
                    if 'dtt' in kwargs:
                        kwargs['dtt'] = None
                    _tl_log("  CACHE HIT -> what replaced: {}".format(repr(what[:80])))
                elif persistent._translator_cache and cache_key in persistent._translator_cache:
                    # Punctuation-only text in cache — delete bad entry, show original
                    del persistent._translator_cache[cache_key]
                    _tl_log("  CACHE CLEANUP -> removed punctuation-only entry")
                elif persistent._translator_auto_translate and _translator_needs_translation(what):
                    store._tl_auto_pending = True
                    # Hide original text while API translates (single space = invisible)
                    what = " "
                    if 'dtt' in kwargs:
                        kwargs['dtt'] = None
                    _tl_log("  CACHE MISS -> auto_pending=True, what=' '")
                elif persistent._translator_auto_translate:
                    _tl_log("  SKIP -> no translatable content (punctuation only)")
                else:
                    _tl_log("  CACHE MISS, auto_translate off -> no action")
            elif persistent._translator_auto_translate and what:
                store._tl_auto_pending = True
                _tl_log("  non-inline auto_pending=True")
            else:
                _tl_log("  no inline/auto path taken")
        _tl_log("  FINAL what passed to original: {}".format(repr(what[:80] if what else None)))
        return _tl_original_display_say(who, what, *args, **kwargs)

    _tl_char_module.display_say = _tl_patched_display_say

    ##########################################################################
    ## 3d-2. Inline translation mode support
    ##   Uses interact_callbacks to modify say screen scope BEFORE screens
    ##   evaluate, so the Text widget naturally picks up the new text.
    ##   Overlay screen then disables slow text so full text shows instantly.
    ##########################################################################

    def _translator_interact_cb():
        """Runs BEFORE screen evaluation on each interaction cycle.
        Modifies say screen scope so the Text widget is created/updated
        with translated text directly — correct layout from the start."""
        if not (persistent._translator_enabled and persistent._translator_inline_mode):
            return
        if not (store._tl_show_translation and store._tl_translated_text):
            return
        try:
            scr = renpy.get_screen("say")
            if scr is not None and hasattr(scr, 'scope') and 'what' in scr.scope:
                translated = store._tl_translated_text
                if scr.scope["what"] != translated:
                    scr.scope["what"] = translated
                    _tl_log("[interact_cb] scope['what'] set to translated: {}".format(repr(translated[:60])))
        except Exception as e:
            _tl_log("[interact_cb] ERROR: {}".format(str(e)))

    config.interact_callbacks.append(_translator_interact_cb)

    # Register keyboard shortcuts via config.keymap
    config.keymap.setdefault('translator_toggle', [])
    if 't' not in config.keymap['translator_toggle']:
        config.keymap['translator_toggle'].append('t')

    config.keymap.setdefault('translator_auto_toggle', [])
    if 'shift_K_t' not in config.keymap['translator_auto_toggle']:
        config.keymap['translator_auto_toggle'].append('shift_K_t')

    def _translator_kill_slow():
        """Disable slow text on the say screen's what widget."""
        try:
            w = renpy.get_widget("say", "what")
            if w is not None:
                w.slow = False
                if hasattr(w, 'slow_done') and w.slow_done is not None:
                    w.slow_done()
                    w.slow_done = None
        except Exception:
            pass

    def _translator_inline_update():
        """Called from overlay screen (after say screen evaluates).
        Backup layer: ensures widget text matches translation even if
        interact_cb scope modification wasn't enough.
        Also kills slow text and ensures full text visibility."""
        if not (store._tl_show_translation and store._tl_translated_text):
            return
        try:
            w = renpy.get_widget("say", "what")
            if w is None:
                return

            plain_what = store._tl_translated_text

            # Check if widget already has correct text (from interact_cb scope change)
            current_text = ""
            if hasattr(w, 'text'):
                if isinstance(w.text, list):
                    current_text = "".join(str(s) for s in w.text)
                else:
                    current_text = str(w.text)

            needs_update = plain_what not in current_text

            if needs_update:
                _tl_log("[inline_update] widget text mismatch, applying set_text. widget={}, target={}".format(
                    repr(current_text[:40]), repr(plain_what[:40])))
                if hasattr(w, 'kill_layout'):
                    w.kill_layout()
                w.set_text(plain_what)
            else:
                _tl_log("[inline_update] widget already has correct text (len={})".format(len(plain_what)))

            # Always kill slow text and ensure full visibility
            w.slow = False
            if hasattr(w, 'slow_done') and w.slow_done is not None:
                w.slow_done()
                w.slow_done = None

            if hasattr(w, 'end'):
                w.end = len(plain_what) * 10

            if hasattr(w, 'dirty'):
                w.dirty = True

            renpy.display.render.redraw(w, 0)

            _tl_log("[inline_update] done. slow={}, end={}".format(
                getattr(w, 'slow', '?'), getattr(w, 'end', '?')))

        except Exception as e:
            _tl_log("[inline_update] ERROR: {}".format(str(e)))

    ##########################################################################
    ## 3e. Gemini API call (runs in background thread)
    ##########################################################################

    # HTTP helper — uses requests if available, falls back to urllib
    try:
        import requests as _tl_requests
        _tl_api_session = _tl_requests.Session()
        _tl_has_requests = True
    except ImportError:
        _tl_has_requests = False

    def _tl_http_post(url, headers=None, json_data=None, data=None, timeout=10):
        """POST request with requests/urllib fallback. Returns (status_code, response_dict_or_None)."""
        if _tl_has_requests:
            if json_data is not None:
                _tl_api_session.headers.update(headers or {})
                r = _tl_api_session.post(url, json=json_data, timeout=timeout)
            else:
                r = _tl_api_session.post(url, headers=headers or {}, data=data, timeout=timeout)
            return r.status_code, r.json() if r.status_code == 200 else None
        else:
            import json
            try:
                from urllib.request import Request, urlopen
                from urllib.parse import urlencode
            except ImportError:
                from urllib2 import Request, urlopen
                from urllib import urlencode
            if json_data is not None:
                body = json.dumps(json_data).encode("utf-8")
                h = dict(headers or {})
                h["Content-Type"] = "application/json"
            elif data is not None:
                body = urlencode(data).encode("utf-8") if isinstance(data, dict) else data
                h = dict(headers or {})
                h.setdefault("Content-Type", "application/x-www-form-urlencoded")
            else:
                body = None
                h = dict(headers or {})
            req = Request(url, data=body, headers=h)
            try:
                resp = urlopen(req, timeout=timeout)
                code = resp.getcode()
                return code, json.loads(resp.read().decode("utf-8")) if code == 200 else None
            except Exception as e:
                if hasattr(e, 'code'):
                    return e.code, None
                raise

    def _tl_http_get(url, params=None, headers=None, timeout=10):
        """GET request with requests/urllib fallback. Returns (status_code, content_bytes)."""
        if _tl_has_requests:
            r = _tl_requests.get(url, params=params, headers=headers or {}, timeout=timeout)
            return r.status_code, r.content
        else:
            try:
                from urllib.request import Request, urlopen
                from urllib.parse import urlencode
            except ImportError:
                from urllib2 import Request, urlopen
                from urllib import urlencode
            if params:
                url = url + "?" + urlencode(params)
            req = Request(url, headers=headers or {})
            try:
                resp = urlopen(req, timeout=timeout)
                return resp.getcode(), resp.read()
            except Exception as e:
                if hasattr(e, 'code'):
                    return e.code, b""
                raise

    def _translator_api_call(text, target_lang, api_key, guard_text):
        """Call Gemini API in a background thread. Updates store variables."""
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"
            clean_text = _translator_strip_tags(text)
            prompt = "Translate to {}. Only output the translation:\n{}".format(target_lang, clean_text)

            status, data = _tl_http_post(
                url,
                headers={"x-goog-api-key": api_key},
                json_data={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0, "maxOutputTokens": 256}
                },
                timeout=10
            )

            if store._tl_current_what != guard_text:
                return

            if status == 200 and data:
                translated = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                cache_key = "{}::{}".format(target_lang, _translator_strip_tags(guard_text))
                if persistent._translator_cache is None:
                    persistent._translator_cache = {}
                persistent._translator_cache[cache_key] = translated

                store._tl_translation_counter += 1
                if store._tl_translation_counter % 100 == 0:
                    if len(persistent._translator_cache) > 5000:
                        keys = list(persistent._translator_cache.keys())
                        to_remove = keys[:len(keys) // 5]
                        for k in to_remove:
                            del persistent._translator_cache[k]

                store._tl_translated_text = translated
                store._tl_show_translation = True
                store._tl_error_message = ""
            elif status == 429:
                store._tl_error_message = "Too many requests. Please wait."
            elif status in (401, 403):
                store._tl_error_message = "Invalid API key. Check settings."
            else:
                store._tl_error_message = "API error (HTTP {}).".format(status)

        except Exception as e:
            if store._tl_current_what == guard_text:
                store._tl_error_message = "Error: {}".format(str(e)[:60])

        finally:
            store._tl_is_translating = False
            try:
                renpy.restart_interaction()
            except Exception:
                pass

    ##########################################################################
    ## 3e-2. DeepL API call (runs in background thread)
    ##########################################################################

    def _translator_api_call_deepl(text, target_lang, api_key, guard_text):
        """Call DeepL API in a background thread. Updates store variables."""
        try:
            lang_code = _translator_deepl_lang_codes.get(target_lang, "EN")
            clean_text = _translator_strip_tags(text)

            status, data = _tl_http_post(
                "https://api-free.deepl.com/v2/translate",
                data={"auth_key": api_key, "text": clean_text, "target_lang": lang_code},
                timeout=15
            )

            if store._tl_current_what != guard_text:
                return

            if status == 200 and data:
                translated = data["translations"][0]["text"].strip()
                cache_key = "{}::{}".format(target_lang, _translator_strip_tags(guard_text))
                if persistent._translator_cache is None:
                    persistent._translator_cache = {}
                persistent._translator_cache[cache_key] = translated

                store._tl_translation_counter += 1
                if store._tl_translation_counter % 100 == 0:
                    if len(persistent._translator_cache) > 5000:
                        keys = list(persistent._translator_cache.keys())
                        to_remove = keys[:len(keys) // 5]
                        for k in to_remove:
                            del persistent._translator_cache[k]

                store._tl_translated_text = translated
                store._tl_show_translation = True
                store._tl_error_message = ""
            elif status == 429:
                store._tl_error_message = "Too many requests. Please wait."
            elif status in (401, 403):
                store._tl_error_message = "Invalid DeepL API key. Check settings."
            else:
                store._tl_error_message = "DeepL error (HTTP {}).".format(status)

        except Exception as e:
            if store._tl_current_what == guard_text:
                store._tl_error_message = "Error: {}".format(str(e)[:60])

        finally:
            store._tl_is_translating = False
            try:
                renpy.restart_interaction()
            except Exception:
                pass

    ##########################################################################
    ## 3e-3. OpenAI API call (runs in background thread)
    ##########################################################################

    def _translator_api_call_openai(text, target_lang, api_key, guard_text):
        """Call OpenAI API in a background thread. Updates store variables."""
        try:
            clean_text = _translator_strip_tags(text)

            status, data = _tl_http_post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": "Bearer " + api_key},
                json_data={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Translate to {}. Only output the translation:\n{}".format(target_lang, clean_text)}],
                    "temperature": 0.3
                },
                timeout=15
            )

            if store._tl_current_what != guard_text:
                return

            if status == 200 and data:
                translated = data["choices"][0]["message"]["content"].strip()
                cache_key = "{}::{}".format(target_lang, _translator_strip_tags(guard_text))
                if persistent._translator_cache is None:
                    persistent._translator_cache = {}
                persistent._translator_cache[cache_key] = translated

                store._tl_translation_counter += 1
                if store._tl_translation_counter % 100 == 0:
                    if len(persistent._translator_cache) > 5000:
                        keys = list(persistent._translator_cache.keys())
                        to_remove = keys[:len(keys) // 5]
                        for k in to_remove:
                            del persistent._translator_cache[k]

                store._tl_translated_text = translated
                store._tl_show_translation = True
                store._tl_error_message = ""
            elif status == 429:
                store._tl_error_message = "Too many requests. Please wait."
            elif status in (401, 403):
                store._tl_error_message = "Invalid OpenAI API key. Check settings."
            else:
                store._tl_error_message = "OpenAI error (HTTP {}).".format(status)

        except Exception as e:
            if store._tl_current_what == guard_text:
                store._tl_error_message = "Error: {}".format(str(e)[:60])

        finally:
            store._tl_is_translating = False
            try:
                renpy.restart_interaction()
            except Exception:
                pass

    ##########################################################################
    ## 3f. Toggle translation (called from overlay button)
    ##########################################################################

    def _translator_toggle():
        """Toggle translation on/off for the current dialogue line."""
        if not store._tl_current_what:
            return

        # If already showing translation, revert to original
        if store._tl_show_translation:
            store._tl_show_translation = False
            return

        # If already translating, do nothing
        if store._tl_is_translating:
            return

        # Select API provider and key
        if persistent._translator_api_provider == "deepl":
            fn = _translator_api_call_deepl
            api_key = persistent._translator_deepl_key
        elif persistent._translator_api_provider == "openai":
            fn = _translator_api_call_openai
            api_key = persistent._translator_openai_key
        else:
            fn = _translator_api_call
            api_key = persistent._translator_api_key

        if not api_key or not api_key.strip():
            store._tl_error_message = "API key required. Enter it in settings."
            return

        target_lang = persistent._translator_target_lang or "English"
        text = store._tl_current_what
        stripped = _translator_strip_tags(text)

        if not stripped.strip():
            return

        # Check cache
        cache_key = "{}::{}".format(target_lang, stripped)
        if persistent._translator_cache and cache_key in persistent._translator_cache:
            store._tl_translated_text = persistent._translator_cache[cache_key]
            store._tl_show_translation = True
            store._tl_error_message = ""
            renpy.restart_interaction()
            return

        # Start API call in background thread
        store._tl_is_translating = True
        store._tl_error_message = ""
        renpy.restart_interaction()

        renpy.invoke_in_thread(
            fn=fn,
            text=text,
            target_lang=target_lang,
            api_key=api_key.strip(),
            guard_text=text
        )

    ##########################################################################
    ## 3g. Settings helpers
    ##########################################################################

    def _translator_open_settings():
        store._tl_settings_visible = True
        renpy.restart_interaction()

    def _translator_close_settings():
        store._tl_settings_visible = False
        renpy.restart_interaction()

    def _translator_set_language(lang):
        persistent._translator_target_lang = lang
        renpy.restart_interaction()

    def _translator_paste_api_key():
        try:
            import subprocess
            result = subprocess.run(
                ['powershell', '-command', 'Get-Clipboard'],
                capture_output=True, text=True, timeout=5
            )
            clip = result.stdout.strip()
            if clip:
                persistent._translator_api_key = clip
        except Exception:
            store._tl_error_message = "Paste failed."
        renpy.restart_interaction()

    def _translator_clear_cache():
        persistent._translator_cache = {}
        renpy.restart_interaction()

    def _translator_toggle_enabled():
        persistent._translator_enabled = not persistent._translator_enabled
        if not persistent._translator_enabled:
            store._tl_show_translation = False
            store._tl_translated_text = ""
            store._tl_error_message = ""
        renpy.restart_interaction()

    def _translator_toggle_auto():
        persistent._translator_auto_translate = not persistent._translator_auto_translate
        renpy.restart_interaction()

    def _translator_toggle_inline():
        persistent._translator_inline_mode = not persistent._translator_inline_mode
        renpy.restart_interaction()

    def _translator_reset_state():
        """Reset all runtime state without clearing cache."""
        store._tl_show_translation = False
        store._tl_translated_text = ""
        store._tl_is_translating = False
        store._tl_error_message = ""
        store._tl_saving_word = ""
        store._tl_auto_pending = False
        store._tl_inline_applied = False
        store._tl_word_select_mode = False
        store._tl_selected_indices = []
        renpy.restart_interaction()

    def _translator_auto_do_translate():
        """Triggered by timer when auto-translate is pending."""
        store._tl_auto_pending = False
        if store._tl_current_what and not store._tl_show_translation and not store._tl_is_translating:
            _translator_toggle()

    ##########################################################################
    ## 3h. Word saving
    ##########################################################################

    def _translator_get_saved_indices(text):
        """Return set of word indices that are part of any saved phrase."""
        if not text or not persistent._translator_saved_words:
            return set()

        import re
        words = text.split()
        saved_indices = set()
        lang = persistent._translator_target_lang or "English"

        for entry in persistent._translator_saved_words:
            if entry.get("lang") != lang:
                continue
            saved_phrase = entry.get("word", "")
            if not saved_phrase:
                continue

            saved_words = saved_phrase.split()
            phrase_len = len(saved_words)

            for i in range(len(words) - phrase_len + 1):
                match = True
                for j in range(phrase_len):
                    clean_w = re.sub(r'[.,!?;:\'\"()\[\]{}\u2026]', '', words[i + j]).strip().lower()
                    if clean_w != saved_words[j].lower():
                        match = False
                        break
                if match:
                    for j in range(phrase_len):
                        saved_indices.add(i + j)

        return saved_indices

    def _translator_save_word(word):
        """Save a word with reverse translation via API."""
        import re
        clean = re.sub(r'[.,!?;:\'\"()\[\]{}\u2026]', '', word).strip()
        if not clean:
            return

        lang = persistent._translator_target_lang or "English"

        # Select API key based on provider
        if persistent._translator_api_provider == "deepl":
            api_key = persistent._translator_deepl_key
        elif persistent._translator_api_provider == "openai":
            api_key = persistent._translator_openai_key
        else:
            api_key = persistent._translator_api_key

        if not api_key or not api_key.strip():
            store._tl_error_message = "API key required."
            renpy.restart_interaction()
            return

        store._tl_saving_word = clean
        renpy.restart_interaction()

        renpy.invoke_in_thread(
            fn=_translator_reverse_translate,
            word=clean,
            source_lang=lang,
            context=store._tl_current_what,
            api_key=api_key.strip(),
            provider=persistent._translator_api_provider
        )

    def _translator_reverse_translate(word, source_lang, context, api_key, provider="gemini"):
        """Reverse translate a word and save it."""
        try:
            prompt = (
                "The word '{}' in {} appears in a translation of this original text: '{}'. "
                "What is the original English word that corresponds to '{}'? "
                "Return ONLY the single original word, nothing else."
            ).format(word, source_lang, context, word)

            if provider == "deepl":
                status, data = _tl_http_post(
                    "https://api-free.deepl.com/v2/translate",
                    data={"auth_key": api_key, "text": word, "target_lang": "EN"},
                    timeout=10
                )
            elif provider == "openai":
                status, data = _tl_http_post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": "Bearer " + api_key},
                    json_data={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3
                    },
                    timeout=10
                )
            else:
                status, data = _tl_http_post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
                    headers={"x-goog-api-key": api_key},
                    json_data={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=10
                )

            if status == 200 and data:
                if provider == "deepl":
                    original = data["translations"][0]["text"].strip()
                elif provider == "openai":
                    original = data["choices"][0]["message"]["content"].strip()
                else:
                    original = data["candidates"][0]["content"]["parts"][0]["text"].strip()

                if persistent._translator_saved_words is None:
                    persistent._translator_saved_words = []

                # Check duplicate by original word
                for entry in persistent._translator_saved_words:
                    if entry.get("original", "").lower() == original.lower():
                        store._tl_error_message = "Already saved!"
                        store._tl_saving_word = ""
                        try:
                            renpy.restart_interaction()
                        except Exception:
                            pass
                        return

                persistent._translator_saved_words.append({
                    "word": word,
                    "original": original,
                    "lang": source_lang
                })

            store._tl_saving_word = ""

        except Exception:
            store._tl_saving_word = ""

        try:
            renpy.restart_interaction()
        except Exception:
            pass

    def _translator_delete_word(index):
        """Delete a saved word by index."""
        if persistent._translator_saved_words and 0 <= index < len(persistent._translator_saved_words):
            persistent._translator_saved_words.pop(index)
        renpy.restart_interaction()

    def _translator_clear_words():
        """Delete all saved words."""
        persistent._translator_saved_words = []
        renpy.restart_interaction()

    ##########################################################################
    ## 3i. Text-to-Speech (Google Translate TTS)
    ##########################################################################

    def _translator_play_word_audio(word):
        """Play TTS audio for an English word."""
        import os
        cache_dir = os.path.join(config.gamedir, "tts_cache")
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in word.lower().strip())
        if not safe_name:
            return
        rel_path = "tts_cache/" + safe_name + ".mp3"
        full_path = os.path.join(cache_dir, safe_name + ".mp3")

        if os.path.exists(full_path):
            try:
                renpy.sound.play(rel_path)
            except Exception:
                pass
        else:
            renpy.invoke_in_thread(
                fn=_translator_tts_download_and_play,
                word=word,
                safe_name=safe_name
            )

    def _translator_tts_download_and_play(word, safe_name):
        """Download TTS MP3 from Google Translate and play it."""
        import os
        try:
            cache_dir = os.path.join(config.gamedir, "tts_cache")
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)

            full_path = os.path.join(cache_dir, safe_name + ".mp3")
            rel_path = "tts_cache/" + safe_name + ".mp3"

            status, content = _tl_http_get(
                "https://translate.google.com/translate_tts",
                params={"ie": "UTF-8", "tl": "en", "client": "tw-ob", "q": word},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=10
            )

            if status == 200 and len(content) > 100:
                with open(full_path, "wb") as f:
                    f.write(content)

                try:
                    renpy.sound.play(rel_path)
                except Exception:
                    pass
            else:
                store._tl_error_message = "TTS failed (HTTP {}).".format(status)

        except Exception as e:
            store._tl_error_message = "TTS error: {}".format(str(e)[:40])

        try:
            renpy.restart_interaction()
        except Exception:
            pass

    ##########################################################################
    ## 3j. Word selection mode
    ##########################################################################

    def _translator_start_word_select(idx):
        """Right-click a word to enter selection mode."""
        store._tl_word_select_mode = True
        store._tl_selected_indices = [idx]
        renpy.restart_interaction()

    def _translator_toggle_word_index(idx):
        """Click a word in selection mode to toggle it."""
        if idx in store._tl_selected_indices:
            store._tl_selected_indices.remove(idx)
        else:
            store._tl_selected_indices.append(idx)
        if not store._tl_selected_indices:
            store._tl_word_select_mode = False
        renpy.restart_interaction()

    def _translator_cancel_word_select():
        """Cancel selection mode."""
        store._tl_word_select_mode = False
        store._tl_selected_indices = []
        renpy.restart_interaction()

    def _translator_save_selected():
        """Save selected words as a phrase."""
        if not store._tl_selected_indices or not store._tl_translated_text:
            return
        words = store._tl_translated_text.split()
        sorted_indices = sorted(store._tl_selected_indices)
        phrase = " ".join(words[i] for i in sorted_indices if i < len(words))
        store._tl_word_select_mode = False
        store._tl_selected_indices = []
        _translator_save_word(phrase)

    ##########################################################################
    ## 3k. Inline font size helpers
    ##########################################################################

    def _translator_adjust_font_size(delta):
        current = persistent._translator_inline_font_size
        if current == 0:
            current = 22  # start from default
        new_val = max(10, min(40, current + delta))
        persistent._translator_inline_font_size = new_val
        renpy.restart_interaction()

    def _translator_reset_font_size():
        persistent._translator_inline_font_size = 0
        renpy.restart_interaction()

    ##########################################################################
    ## 3l. Inline word click helpers
    ##########################################################################

    def _translator_inline_word_click(word, ypos):
        """Show save popup for a word in inline mode."""
        store._tl_inline_word_popup = word
        store._tl_inline_word_popup_y = ypos
        renpy.restart_interaction()

    def _translator_inline_word_dismiss():
        store._tl_inline_word_popup = ""
        renpy.restart_interaction()

    ##########################################################################
    ## 3m. XLSX export for saved words
    ##########################################################################

    def _translator_export_words_xlsx():
        """Export saved words to XLSX using zipfile+XML (no external deps)."""
        import os, zipfile

        if not persistent._translator_saved_words:
            store._tl_error_message = "No words to export."
            renpy.restart_interaction()
            return

        export_path = os.path.join(config.basedir, "saved_words.xlsx")

        def _xml_escape(s):
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        # Build shared strings
        strings = ["Word", "Original", "Language"]
        for entry in persistent._translator_saved_words:
            strings.append(_xml_escape(entry.get("word", "")))
            strings.append(_xml_escape(entry.get("original", "")))
            strings.append(_xml_escape(entry.get("lang", "")))

        shared_strings_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        shared_strings_xml += '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{}" uniqueCount="{}">'.format(len(strings), len(strings))
        for s in strings:
            shared_strings_xml += '<si><t>{}</t></si>'.format(s)
        shared_strings_xml += '</sst>'

        # Build sheet data
        sheet_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        sheet_xml += '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        sheet_xml += '<cols><col min="1" max="1" width="25"/><col min="2" max="2" width="25"/><col min="3" max="3" width="15"/></cols>'
        sheet_xml += '<sheetData>'
        # Header row
        sheet_xml += '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>'
        # Data rows
        for i, entry in enumerate(persistent._translator_saved_words):
            row_num = i + 2
            si_base = 3 + i * 3
            sheet_xml += '<row r="{}"><c r="A{}" t="s"><v>{}</v></c><c r="B{}" t="s"><v>{}</v></c><c r="C{}" t="s"><v>{}</v></c></row>'.format(
                row_num, row_num, si_base, row_num, si_base + 1, row_num, si_base + 2)
        sheet_xml += '</sheetData></worksheet>'

        content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        content_types += '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        content_types += '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        content_types += '<Default Extension="xml" ContentType="application/xml"/>'
        content_types += '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        content_types += '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        content_types += '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        content_types += '</Types>'

        rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        rels += '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        rels += '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        rels += '</Relationships>'

        workbook_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        workbook_xml += '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        workbook_xml += '<sheets><sheet name="Saved Words" sheetId="1" r:id="rId1"/></sheets></workbook>'

        workbook_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        workbook_rels += '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        workbook_rels += '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        workbook_rels += '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        workbook_rels += '</Relationships>'

        try:
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('[Content_Types].xml', content_types)
                zf.writestr('_rels/.rels', rels)
                zf.writestr('xl/workbook.xml', workbook_xml)
                zf.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
                zf.writestr('xl/worksheets/sheet1.xml', sheet_xml)
                zf.writestr('xl/sharedStrings.xml', shared_strings_xml)

            store._tl_error_message = "Exported to saved_words.xlsx"
        except Exception as e:
            store._tl_error_message = "Export failed: {}".format(str(e)[:40])

        renpy.restart_interaction()

    ##########################################################################
    ## 3n. API key paste helpers for DeepL and OpenAI
    ##########################################################################

    def _translator_paste_deepl_key():
        try:
            import subprocess
            result = subprocess.run(
                ['powershell', '-command', 'Get-Clipboard'],
                capture_output=True, text=True, timeout=5
            )
            clip = result.stdout.strip()
            if clip:
                persistent._translator_deepl_key = clip
        except Exception:
            store._tl_error_message = "Paste failed."
        renpy.restart_interaction()

    def _translator_paste_openai_key():
        try:
            import subprocess
            result = subprocess.run(
                ['powershell', '-command', 'Get-Clipboard'],
                capture_output=True, text=True, timeout=5
            )
            clip = result.stdout.strip()
            if clip:
                persistent._translator_openai_key = clip
        except Exception:
            store._tl_error_message = "Paste failed."
        renpy.restart_interaction()

################################################################################
## 4. OVERLAY SCREEN — Translation button + translated text display
################################################################################

screen _translator_overlay():

    zorder 90

    # Settings gear button — always visible top right
    textbutton "{font=DejaVuSans.ttf}\u2699{/font}":
        xalign 0.98
        yalign 0.02
        text_size 32
        if persistent._translator_enabled:
            text_color "#ccccccaa"
            text_hover_color "#ffffffee"
        else:
            text_color "#66666666"
            text_hover_color "#aaaaaabb"
        action Function(_translator_open_settings)

    if persistent._translator_enabled:

        # Inline mode: replace say widget text with translation + kill slow text
        # This runs AFTER say screen evaluates (overlay zorder 90 > say screen)
        if persistent._translator_inline_mode and _tl_show_translation and _tl_translated_text:
            $ _translator_inline_update()
            $ _translator_kill_slow()

        # Keyboard shortcuts
        if _tl_current_what:
            key "translator_toggle" action Function(_translator_toggle)
            key "translator_auto_toggle" action Function(_translator_toggle_auto)

        # Translation button — only visible when dialogue is showing
        if _tl_current_what:

            if _tl_is_translating:
                # Loading state
                frame:
                    xalign 0.98
                    yalign 0.88
                    padding (12, 8, 12, 8)
                    background Frame(Solid("#333333cc"), 4, 4)
                    text "..." size 18 color "#ffcc00" font "DejaVuSans.ttf"

            else:
                # Translation toggle button
                textbutton "TR":
                    xalign 0.98
                    yalign 0.88
                    text_size 16
                    text_color "#ffffff"
                    text_bold True
                    text_font "DejaVuSans.ttf"
                    if _tl_show_translation:
                        background Frame(Solid("#2a7a2acc"), 4, 4)
                    else:
                        background Frame(Solid("#333333cc"), 4, 4)
                    hover_background Frame(Solid("#555555ee"), 4, 4)
                    padding (12, 8, 12, 8)
                    action Function(_translator_toggle)

            # Auto-translate toggle button — below TR
            hbox:
                xalign 0.98
                yalign 0.92
                spacing 4
                # Auto-translate toggle
                textbutton "A":
                    text_size 13
                    text_bold True
                    text_font "DejaVuSans.ttf"
                    if persistent._translator_auto_translate:
                        text_color "#44cc44"
                        background Frame(Solid("#2a7a2acc"), 4, 4)
                    else:
                        text_color "#888888"
                        background Frame(Solid("#333333cc"), 4, 4)
                    hover_background Frame(Solid("#555555ee"), 4, 4)
                    padding (10, 5, 10, 5)
                    action Function(_translator_toggle_auto)
                # Reset button
                textbutton "{font=DejaVuSans.ttf}\u21BB{/font}":
                    text_size 13
                    text_color "#cc8844"
                    text_hover_color "#ffaa66"
                    background Frame(Solid("#333333cc"), 4, 4)
                    hover_background Frame(Solid("#555555ee"), 4, 4)
                    padding (10, 5, 10, 5)
                    action Function(_translator_reset_state)

            # Auto-translate timer
            if _tl_auto_pending:
                timer 0.05 action Function(_translator_auto_do_translate)

        # Error message display
        if _tl_error_message:
            frame:
                xalign 0.5
                yalign 0.82
                padding (20, 10, 20, 10)
                background Frame(Solid("#aa3333dd"), 4, 4)
                text "[_tl_error_message]" size 16 color "#ffffff" font "DejaVuSans.ttf"
            timer 4.0 action SetVariable("_tl_error_message", "")

    # Settings panel (modal-ish)
    if _tl_settings_visible:
        use _translator_settings

    # Translated text overlay — right-click to select words, then save
    if _tl_show_translation and _tl_translated_text and _tl_current_what and not persistent._translator_inline_mode:
        frame:
            xalign 0.5
            yalign 0.76
            xmaximum 0.85
            padding (30, 20, 30, 20)
            background Frame(Solid("#1a1a1aee"), 6, 6)
            vbox:
                spacing 6
                if _tl_current_who:
                    text "[_tl_current_who]" size 20 color "#ffcc44" bold True font "DejaVuSans.ttf"

                # Word selection hint
                if _tl_word_select_mode:
                    text "Click words to select, then Save" size 13 color "#aaaaaa" font "DejaVuSans.ttf"

                $ _tl_clean_text = _translator_strip_tags(_tl_translated_text)
                $ _tl_saved_idx = _translator_get_saved_indices(_tl_clean_text)
                hbox:
                    box_wrap True
                    spacing 6
                    for _tl_i, _tl_w in enumerate(_tl_clean_text.split()):

                        if _tl_word_select_mode:
                            # SELECTION MODE
                            if _tl_i in _tl_selected_indices:
                                # Selected — yellow highlight
                                textbutton "[_tl_w]":
                                    text_size 22
                                    text_color "#ffdd00"
                                    text_bold True
                                    text_font "DejaVuSans.ttf"
                                    background Frame(Solid("#ffdd0033"), 2, 2)
                                    padding (3, 1, 3, 1)
                                    action Function(_translator_toggle_word_index, _tl_i)
                                    alternate Function(_translator_toggle_word_index, _tl_i)
                            else:
                                # Not selected — dim
                                textbutton "[_tl_w]":
                                    text_size 22
                                    text_color "#999999"
                                    text_hover_color "#ffffff"
                                    text_font "DejaVuSans.ttf"
                                    padding (3, 1, 3, 1)
                                    action Function(_translator_toggle_word_index, _tl_i)
                                    alternate Function(_translator_toggle_word_index, _tl_i)
                        else:
                            # NORMAL MODE
                            if _tl_i in _tl_saved_idx:
                                # Saved word/phrase — green
                                textbutton "[_tl_w]":
                                    text_size 22
                                    text_color "#88ddaa"
                                    text_hover_color "#aaffcc"
                                    text_font "DejaVuSans.ttf"
                                    padding (0, 0, 0, 0)
                                    action NullAction()
                                    alternate Function(_translator_start_word_select, _tl_i)
                            else:
                                textbutton "[_tl_w]":
                                    text_size 22
                                    text_color "#ffffff"
                                    text_hover_color "#ffdd66"
                                    text_font "DejaVuSans.ttf"
                                    padding (0, 0, 0, 0)
                                    action NullAction()
                                    alternate Function(_translator_start_word_select, _tl_i)

                # Selection mode buttons
                if _tl_word_select_mode:
                    hbox:
                        spacing 15
                        textbutton "Save":
                            text_size 17
                            text_color "#44cc44"
                            text_hover_color "#66ff66"
                            text_bold True
                            text_font "DejaVuSans.ttf"
                            action Function(_translator_save_selected)
                        textbutton "Cancel":
                            text_size 17
                            text_color "#ff6666"
                            text_hover_color "#ff9999"
                            text_font "DejaVuSans.ttf"
                            action Function(_translator_cancel_word_select)

                if _tl_saving_word:
                    text "Saving '[_tl_saving_word]'..." size 14 color "#ffcc00" font "DejaVuSans.ttf"

################################################################################
## 5. SETTINGS SCREEN
################################################################################

screen _translator_settings():

    zorder 100
    modal True

    # Dark overlay behind settings
    button:
        background Solid("#00000099")
        xfill True
        yfill True
        action Function(_translator_close_settings)

    frame:
        xalign 0.5
        yalign 0.5
        xminimum 520
        xmaximum 620
        padding (30, 25, 30, 25)
        background Frame(Solid("#222222ee"), 8, 8)

        vbox:
            spacing 12

            # Title bar + close
            hbox:
                xfill True
                text "Translation Mod" size 24 color "#ffffff" bold True font "DejaVuSans.ttf"
                textbutton "X":
                    text_size 20
                    text_color "#ff6666"
                    text_hover_color "#ff9999"
                    text_font "DejaVuSans.ttf"
                    xalign 1.0
                    action Function(_translator_close_settings)

            # Tab buttons
            $ _sw_count = len(persistent._translator_saved_words) if persistent._translator_saved_words else 0
            hbox:
                spacing 10
                textbutton "Settings":
                    text_size 18
                    text_font "DejaVuSans.ttf"
                    if _tl_settings_tab == "settings":
                        text_color "#ffffff"
                        text_bold True
                        background Frame(Solid("#444444cc"), 4, 4)
                    else:
                        text_color "#888888"
                        text_hover_color "#cccccc"
                    padding (14, 6, 14, 6)
                    action SetVariable("_tl_settings_tab", "settings")
                if _sw_count > 0:
                    textbutton "Saved Words ([_sw_count])":
                        text_size 18
                        text_font "DejaVuSans.ttf"
                        if _tl_settings_tab == "words":
                            text_color "#ffffff"
                            text_bold True
                            background Frame(Solid("#444444cc"), 4, 4)
                        else:
                            text_color "#888888"
                            text_hover_color "#cccccc"
                        padding (14, 6, 14, 6)
                        action SetVariable("_tl_settings_tab", "words")
                else:
                    textbutton "Saved Words":
                        text_size 18
                        text_font "DejaVuSans.ttf"
                        if _tl_settings_tab == "words":
                            text_color "#ffffff"
                            text_bold True
                            background Frame(Solid("#444444cc"), 4, 4)
                        else:
                            text_color "#888888"
                            text_hover_color "#cccccc"
                        padding (14, 6, 14, 6)
                        action SetVariable("_tl_settings_tab", "words")

            null height 5

            ##############################################################
            ## SETTINGS TAB
            ##############################################################
            if _tl_settings_tab == "settings":

                # Enable / Disable toggle
                hbox:
                    spacing 10
                    text "Mod Status:" size 18 color "#cccccc" yalign 0.5 font "DejaVuSans.ttf"
                    if persistent._translator_enabled:
                        textbutton "Enabled":
                            text_size 18
                            text_color "#44cc44"
                            text_hover_color "#66ee66"
                            text_font "DejaVuSans.ttf"
                            action Function(_translator_toggle_enabled)
                    else:
                        textbutton "Disabled":
                            text_size 18
                            text_color "#cc4444"
                            text_hover_color "#ee6666"
                            text_font "DejaVuSans.ttf"
                            action Function(_translator_toggle_enabled)

                # Translation Mode toggle
                hbox:
                    spacing 10
                    text "Translation Mode:" size 18 color "#cccccc" yalign 0.5 font "DejaVuSans.ttf"
                    if persistent._translator_inline_mode:
                        textbutton "Inline (Replace Text)":
                            text_size 18
                            text_color "#66aaff"
                            text_hover_color "#99ccff"
                            text_font "DejaVuSans.ttf"
                            action Function(_translator_toggle_inline)
                    else:
                        textbutton "Overlay (Panel)":
                            text_size 18
                            text_color "#ffcc44"
                            text_hover_color "#ffdd66"
                            text_font "DejaVuSans.ttf"
                            action Function(_translator_toggle_inline)

                # Inline font size control
                if persistent._translator_inline_mode:
                    hbox:
                        spacing 10
                        text "Inline Font Size:" size 18 color "#cccccc" yalign 0.5 font "DejaVuSans.ttf"
                        textbutton "-":
                            text_size 18
                            text_color "#ff8844"
                            text_hover_color "#ffaa66"
                            text_font "DejaVuSans.ttf"
                            text_bold True
                            padding (8, 3, 8, 3)
                            background Frame(Solid("#333333cc"), 4, 4)
                            hover_background Frame(Solid("#555555ee"), 4, 4)
                            action Function(_translator_adjust_font_size, -2)
                        $ _fs_label = str(persistent._translator_inline_font_size) if persistent._translator_inline_font_size > 0 else "Auto"
                        text "[_fs_label]" size 18 color "#66aaff" yalign 0.5 font "DejaVuSans.ttf"
                        textbutton "+":
                            text_size 18
                            text_color "#44cc44"
                            text_hover_color "#66ee66"
                            text_font "DejaVuSans.ttf"
                            text_bold True
                            padding (8, 3, 8, 3)
                            background Frame(Solid("#333333cc"), 4, 4)
                            hover_background Frame(Solid("#555555ee"), 4, 4)
                            action Function(_translator_adjust_font_size, 2)
                        if persistent._translator_inline_font_size > 0:
                            textbutton "Reset":
                                text_size 14
                                text_color "#888888"
                                text_hover_color "#cccccc"
                                text_font "DejaVuSans.ttf"
                                yalign 0.5
                                action Function(_translator_reset_font_size)

                null height 3

                # API Provider selection
                hbox:
                    spacing 8
                    text "API:" size 18 color "#cccccc" yalign 0.5 font "DejaVuSans.ttf"
                    for _prov, _prov_label, _prov_color in [("gemini", "Gemini", "#ffcc44"), ("deepl", "DeepL", "#0F2B46"), ("openai", "OpenAI", "#10a37f")]:
                        textbutton _prov_label:
                            text_size 16
                            text_font "DejaVuSans.ttf"
                            if persistent._translator_api_provider == _prov:
                                text_color _prov_color
                                text_bold True
                                background Frame(Solid("#444444cc"), 4, 4)
                            else:
                                text_color "#888888"
                                text_hover_color "#cccccc"
                            padding (10, 5, 10, 5)
                            action SetField(persistent, "_translator_api_provider", _prov)

                null height 3

                # API Key — show based on selected provider
                if persistent._translator_api_provider == "gemini":
                    text "Gemini API Key:" size 18 color "#cccccc" font "DejaVuSans.ttf"
                    hbox:
                        spacing 10
                        if persistent._translator_api_key:
                            $ _tl_key_display = persistent._translator_api_key[:8] + "..." + persistent._translator_api_key[-4:] if len(persistent._translator_api_key) > 12 else persistent._translator_api_key
                            text "[_tl_key_display]" size 16 color "#88cc88" font "DejaVuSans.ttf" yalign 0.5
                        else:
                            text "No key set" size 16 color "#aa6666" font "DejaVuSans.ttf" yalign 0.5
                        textbutton "Paste":
                            text_size 16
                            text_color "#66aaff"
                            text_hover_color "#99ccff"
                            text_font "DejaVuSans.ttf"
                            yalign 0.5
                            action Function(_translator_paste_api_key)
                        textbutton "Clear":
                            text_size 16
                            text_color "#ff6666"
                            text_hover_color "#ff9999"
                            text_font "DejaVuSans.ttf"
                            yalign 0.5
                            action SetField(persistent, "_translator_api_key", "")

                elif persistent._translator_api_provider == "deepl":
                    text "DeepL API Key:" size 18 color "#cccccc" font "DejaVuSans.ttf"
                    hbox:
                        spacing 10
                        if persistent._translator_deepl_key:
                            $ _tl_dk_display = persistent._translator_deepl_key[:8] + "..." + persistent._translator_deepl_key[-4:] if len(persistent._translator_deepl_key) > 12 else persistent._translator_deepl_key
                            text "[_tl_dk_display]" size 16 color "#88cc88" font "DejaVuSans.ttf" yalign 0.5
                        else:
                            text "No key set" size 16 color "#aa6666" font "DejaVuSans.ttf" yalign 0.5
                        textbutton "Paste":
                            text_size 16
                            text_color "#66aaff"
                            text_hover_color "#99ccff"
                            text_font "DejaVuSans.ttf"
                            yalign 0.5
                            action Function(_translator_paste_deepl_key)
                        textbutton "Clear":
                            text_size 16
                            text_color "#ff6666"
                            text_hover_color "#ff9999"
                            text_font "DejaVuSans.ttf"
                            yalign 0.5
                            action SetField(persistent, "_translator_deepl_key", "")

                elif persistent._translator_api_provider == "openai":
                    text "OpenAI API Key:" size 18 color "#cccccc" font "DejaVuSans.ttf"
                    hbox:
                        spacing 10
                        if persistent._translator_openai_key:
                            $ _tl_ok_display = persistent._translator_openai_key[:8] + "..." + persistent._translator_openai_key[-4:] if len(persistent._translator_openai_key) > 12 else persistent._translator_openai_key
                            text "[_tl_ok_display]" size 16 color "#88cc88" font "DejaVuSans.ttf" yalign 0.5
                        else:
                            text "No key set" size 16 color "#aa6666" font "DejaVuSans.ttf" yalign 0.5
                        textbutton "Paste":
                            text_size 16
                            text_color "#66aaff"
                            text_hover_color "#99ccff"
                            text_font "DejaVuSans.ttf"
                            yalign 0.5
                            action Function(_translator_paste_openai_key)
                        textbutton "Clear":
                            text_size 16
                            text_color "#ff6666"
                            text_hover_color "#ff9999"
                            text_font "DejaVuSans.ttf"
                            yalign 0.5
                            action SetField(persistent, "_translator_openai_key", "")

                null height 3

                # Language selection
                text "Target Language:" size 18 color "#cccccc" font "DejaVuSans.ttf"

                viewport:
                    xfill True
                    ymaximum 220
                    mousewheel True
                    scrollbars "vertical"
                    draggable True

                    vbox:
                        spacing 4
                        for lang in _translator_languages:
                            textbutton lang:
                                text_size 16
                                text_font "DejaVuSans.ttf"
                                if persistent._translator_target_lang == lang:
                                    text_color "#44cc44"
                                    text_bold True
                                else:
                                    text_color "#aaaaaa"
                                text_hover_color "#ffffff"
                                xfill True
                                action Function(_translator_set_language, lang)

                null height 3

                # Cache info
                hbox:
                    spacing 10
                    $ _cache_count = len(persistent._translator_cache) if persistent._translator_cache else 0
                    text "Cache: [_cache_count] entries" size 16 color "#999999" yalign 0.5 font "DejaVuSans.ttf"
                    textbutton "Clear Cache":
                        text_size 16
                        text_color "#ff8844"
                        text_hover_color "#ffaa66"
                        text_font "DejaVuSans.ttf"
                        action Function(_translator_clear_cache)

                null height 5
                text "Get your API key from:" size 14 color "#888888" font "DejaVuSans.ttf"
                if persistent._translator_api_provider == "deepl":
                    text "deepl.com/pro-api" size 14 color "#6699cc" font "DejaVuSans.ttf"
                elif persistent._translator_api_provider == "openai":
                    text "platform.openai.com/api-keys" size 14 color "#6699cc" font "DejaVuSans.ttf"
                else:
                    text "aistudio.google.com/apikey" size 14 color "#6699cc" font "DejaVuSans.ttf"
                text "Shortcuts: T = translate, Shift+T = auto" size 13 color "#666666" font "DejaVuSans.ttf"

            ##############################################################
            ## SAVED WORDS TAB
            ##############################################################
            elif _tl_settings_tab == "words":

                if persistent._translator_saved_words:

                    hbox:
                        xfill True
                        $ _sw_total = len(persistent._translator_saved_words)
                        text "[_sw_total] saved words" size 16 color "#999999" font "DejaVuSans.ttf" yalign 0.5
                        hbox:
                            spacing 10
                            xalign 1.0
                            textbutton "Export XLSX":
                                text_size 16
                                text_color "#66aaff"
                                text_hover_color "#99ccff"
                                text_font "DejaVuSans.ttf"
                                action Function(_translator_export_words_xlsx)
                            textbutton "Clear All":
                                text_size 16
                                text_color "#ff6666"
                                text_hover_color "#ff9999"
                                text_font "DejaVuSans.ttf"
                                action Function(_translator_clear_words)

                    null height 5

                    viewport:
                        xfill True
                        ymaximum 400
                        mousewheel True
                        scrollbars "vertical"
                        draggable True

                        vbox:
                            spacing 6
                            for _tl_idx, _tl_entry in enumerate(persistent._translator_saved_words):
                                $ _tl_w_word = _tl_entry.get("word", "")
                                $ _tl_w_orig = _tl_entry.get("original", "")
                                $ _tl_w_lang = _tl_entry.get("lang", "")
                                hbox:
                                    xfill True
                                    spacing 8
                                    text "[_tl_w_word]" size 17 color "#88ddaa" font "DejaVuSans.ttf" yalign 0.5 min_width 140
                                    text "-" size 17 color "#666666" font "DejaVuSans.ttf" yalign 0.5
                                    text "[_tl_w_orig]" size 17 color "#cccccc" font "DejaVuSans.ttf" yalign 0.5
                                    # Play pronunciation
                                    textbutton "{font=DejaVuSans.ttf}\u25B6{/font}":
                                        text_size 15
                                        text_color "#66aaff"
                                        text_hover_color "#99ccff"
                                        yalign 0.5
                                        action Function(_translator_play_word_audio, _tl_w_orig)
                                    # Delete
                                    textbutton "x":
                                        text_size 15
                                        text_color "#aa4444"
                                        text_hover_color "#ff6666"
                                        text_font "DejaVuSans.ttf"
                                        yalign 0.5
                                        xalign 1.0
                                        action Function(_translator_delete_word, _tl_idx)

                else:
                    null height 30
                    text "No saved words yet." size 18 color "#888888" font "DejaVuSans.ttf" xalign 0.5
                    null height 10
                    text "Right-click any word in the" size 15 color "#666666" font "DejaVuSans.ttf" xalign 0.5
                    text "translated text to save it." size 15 color "#666666" font "DejaVuSans.ttf" xalign 0.5

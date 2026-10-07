# Messenger preview assets

Used in the scripted landing-page previews; they do not connect to messenger accounts.

- `whatsapp-wallpaper.png`: original transparent wallpaper tile from the [WhatsApp CDN](https://static.whatsapp.net/rsrc.php/v3/yl/r/gi_DckOUM5a.png). Kept unchanged; CSS composites it over the light chat background.
- `telegram-pattern.svg`: original pattern from [Telegram Web A](https://github.com/Ajaxy/telegram-tt/blob/master/src/assets/pattern.svg). Kept unchanged. Repository license is included as `LICENSE.telegram.txt` (GPL v3).
- Telegram's light background uses the four default colors from [wallpaper.ts](https://github.com/Ajaxy/telegram-tt/blob/master/src/util/wallpaper.ts): `#bdcd8c`, `#8eba89`, `#83b28f`, `#c5d3b0`. The preview renders a static CSS gradient.
- WhatsApp's inline icon path is from [Simple Icons](https://github.com/simple-icons/simple-icons/blob/develop/icons/whatsapp.svg), whose [license is CC0](https://github.com/simple-icons/simple-icons/blob/develop/LICENSE.md). The mark is rendered in white; brand names and marks belong to their respective owners.

Retrieved 2026-10-07. Assets are served locally; previews make no requests to these sources at runtime.

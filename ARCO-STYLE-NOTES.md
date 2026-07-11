# PicGen Arco Design Language Notes

Phase 0 source snapshot:

- `arco-design/arco-design` commit `79516eebaaf11f3459508f2579dd851e4e76a22f`, package `@arco-design/web-react` `2.66.15`.
- `arco-design/color` commit `d882db3e3e2574e7c8bc62146aedea21e96c78ec`, package `@arco-design/color` `0.4.0`.
- Both repositories are MIT licensed. The icon sprite retains ByteDance's copyright and MIT text in `static/icons.svg`.
- Values below were read from the official repositories, chiefly `components/style/theme`, each component's `style/token.less` and `style/*.less`, and `icon/_svgs`. The official web spec was also requested, but its response could not be decoded in this environment; no secondary source or remembered value was substituted.
- Phase 0 visual proof: `acceptance-shots/arco-style-tile.png` (1440px review surface, 30 visible icons, no horizontal overflow).

The `--ux-*` variables at the top of `static/styles.css` are the normative implementation. Values labeled “PicGen mapping” are deliberate adaptations required by `TASK-UX-IMPLEMENT.md`; all other measurements are direct Arco values.

## 1. Color System

### Brand palette

The following palette is the actual output of `@arco-design/color` for PicGen brand green `#009568`. Primary component state order follows Arco: normal level 6, hover level 5, active level 7, disabled light level 3.

| Level | Hex | PicGen use |
|---|---|---|
| 1 | `#E8FFF4` | selected-card and selected-tag light surface |
| 2 | `#AAEACE` | focus ring and subtle progress track |
| 3 | `#74D5AE` | disabled primary fill and strong light border |
| 4 | `#46BF93` | card hover border and secondary emphasis |
| 5 | `#1FAA7C` | primary hover |
| 6 | `#009568` | brand and primary default |
| 7 | `#008360` | primary active |
| 8 | `#007156` | readable brand text on levels 1-2 |
| 9 | `#005F4C` | high-emphasis brand text |
| 10 | `#004D40` | deepest brand contrast |

The primary button may use the restrained vertical token `linear-gradient(180deg, #009568, #008B63)`. The end color differs only slightly in lightness and never crosses hue families. Hover and active replace it with solid levels 5 and 7 so states remain unambiguous.

### Neutral hierarchy

Official neutrals are `N1 #F7F8FA`, `N2 #F2F3F5`, `N3 #E5E6EB`, `N4 #C9CDD4`, `N5 #A9AEB8`, `N6 #86909C`, `N7 #6B7785`, `N8 #4E5969`, `N9 #272E3B`, `N10 #1D2129`.

| Semantic token | Official mapping | Use |
|---|---|---|
| `text-1` | `N10 #1D2129` | headings and primary content |
| `text-2` | `N8 #4E5969` | ordinary secondary content |
| `text-3` | `N6 #86909C` | hints, metadata, placeholders |
| `text-4` | `N4 #C9CDD4` | disabled content |
| `fill-1` | `N1 #F7F8FA` | weakest neutral surface |
| `fill-2` | `N2 #F2F3F5` | input/default secondary surface |
| `fill-3` | `N3 #E5E6EB` | input hover and stronger surface |
| `fill-4` | `N4 #C9CDD4` | active neutral surface |
| `border-1` | `N2 #F2F3F5` | internal/very light separation |
| `border-2` | `N3 #E5E6EB` | normal component border |
| `border-3` | `N4 #C9CDD4` | hover/strong border |
| `border-4` | `N6 #86909C` | maximum neutral border contrast |

### Functional colors

| Meaning | Light surface | Hover | Regular | Active | Dark text |
|---|---|---|---|---|---|
| Success | `#E8FFEA` | `#23C343` | `#00B42A` | `#009A29` | `#006622` |
| Warning | `#FFF7E8` | `#FF9A2E` | `#FF7D00` | `#D25F00` | `#792E00` |
| Error | `#FFECE8` | `#F76560` | `#F53F3F` | `#CB272D` | `#770813` |
| Link/info | `#E8F3FF` | `#4080FF` | `#165DFF` | `#0E42D2` | `#031A79` |

Blue is retained only for conventional links and information feedback; it is never the product primary color.

Sources: `@arco-design/color`; `components/style/theme/color/colors.less`; `compiled-colors.less`; `global.less` text/fill/border mappings.

## 2. Typography

Official Arco sizes are Body 1 `12px`, Body 2 `13px`, Body 3 `14px`, Title 1 `16px`, Title 2 `20px`, Title 3 `24px`, Display 1 `36px`, Display 2 `48px`, and Display 3 `56px`. The base component line-height is `1.5715`.

PicGen's fixed pairs avoid viewport-scaled type and make Chinese layout predictable:

| Role | Size / line-height | Weight | Rule |
|---|---|---|---|
| Caption | `12px / 20px` | `400` | pixel dimensions and helper text |
| Small body | `13px / 20px` | `400` | metadata and card subtitles |
| Body | `14px / 22px` | `400` | inputs, descriptions, normal buttons |
| Compact title | `16px / 24px` | `500` | card title and form section title |
| Page heading | `20px / 28px` | `600` | simple-mode form heading |
| Display | `24px / 34px` | `600` | scenario chooser heading only |

Weight `500` marks interactive labels, selected states, and compact titles. Weight `600` is reserved for page/section hierarchy and primary numeric totals. Body text stays `400`; no new simple-mode element uses `700+`.

The font stack is `-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Noto Sans", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif`. Elapsed times, dimensions, counters, and job IDs use `font-variant-numeric: tabular-nums`; dense IDs may also use the `--ux-font-mono` stack.

Sources: `components/style/theme/global.less`, `components/style/theme/default.less`, and component token files.

## 3. Icon System

All new simple-mode icons come from the official Arco outline set at commit `79516e...`. The source root is `icon/_svgs`; every selected source has `viewBox="0 0 48 48"`, root `fill="none"`, `stroke="currentColor"`, and `stroke-width="4"`. Visible strokes use `stroke-linecap="butt"` and default miter joins. `send.svg` retains `stroke-miterlimit="3.8637"`; `image.svg` and `more.svg` retain their official filled subpaths.

`static/icons.svg` moves root inheritance to `<symbol>` and removes fixed width/height. Instances use `<svg aria-hidden="true"><use href="icons.svg#icon-name"></use></svg>`; accessible buttons carry text or an `aria-label`. Loading rotates the outer `<svg>`, not the official path.

| Symbol | Official source under `icon/_svgs/` | Interface location |
|---|---|---|
| `icon-upload` | `interactive-button/outline/upload.svg` | edit/upload card and reference upload |
| `icon-image` | `general/outline/image.svg` | poster card, image placeholders |
| `icon-edit` | `edit/outline/edit.svg` | edit card and “改这张图” |
| `icon-location` | `general/outline/location.svg` | itinerary card and stops |
| `icon-calendar` | `general/outline/calendar.svg` | itinerary dates |
| `icon-list` | `interactive-button/outline/list.svg` | list/ranking card |
| `icon-download` | `interactive-button/outline/download.svg` | download primary action |
| `icon-share-alt` | `interactive-button/outline/share-alt.svg` | share action |
| `icon-refresh` | `interactive-button/outline/refresh.svg` | regenerate and refresh |
| `icon-close` | `tips/outline/close.svg` | dialogs, upload removal, checklist close |
| `icon-check` | `tips/outline/check.svg` | completed step and success |
| `icon-exclamation-circle` | `tips/outline/exclamation-circle.svg` | warning and error feedback |
| `icon-info-circle` | `tips/outline/info-circle.svg` | informational feedback and timing |
| `icon-loading` | `general/outline/loading.svg` | button and panel loading |
| `icon-arrow-left` | `direction/outline/arrow-left.svg` | back to scenarios |
| `icon-arrow-right` | `direction/outline/arrow-right.svg` | enter scenario / next |
| `icon-arrow-down` | `direction/outline/arrow-down.svg` | menus and disclosure |
| `icon-arrow-up` | `direction/outline/arrow-up.svg` | expanded disclosure |
| `icon-zoom-in` | `edit/outline/zoom-in.svg` | preview zoom in |
| `icon-zoom-out` | `edit/outline/zoom-out.svg` | preview zoom out |
| `icon-history` | `interactive-button/outline/history.svg` | version history |
| `icon-settings` | `interactive-button/outline/settings.svg` | settings/account actions |
| `icon-user` | `general/outline/user.svg` | account/share recipient |
| `icon-send` | `interactive-button/outline/send.svg` | feedback/share message submit |
| `icon-plus` | `tips/outline/plus.svg` | dynamic list item |
| `icon-more` | `interactive-button/outline/more.svg` | result “更多” menu |
| `icon-copy` | `edit/outline/copy.svg` | copy prompt |
| `icon-delete` | `edit/outline/delete.svg` | remove dynamic item |
| `icon-clock-circle` | `tips/outline/clock-circle.svg` | estimated/recent duration |
| `icon-file-image` | `general/outline/file-image.svg` | image file and empty result |

Characters such as `▧`, `◩`, `▶`, `⬆`, `✎`, and emoji are forbidden as new simple-mode icons. Professional-mode legacy glyphs are deliberately untouched.

## 4. Gradients And Decoration

Allowed gradients have one narrow purpose and exact values:

- Scene cover text protection: `linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.4))`, applied only to the lower text region.
- Primary button: `linear-gradient(180deg, #009568, #008B63)` in default state; the same hue and a lightness delta below 6%.
- Progress fill: solid `#009568`, or the same default primary gradient where progress already uses a gradient; the track is `#E5E6EB`.
- Skeleton shimmer: `linear-gradient(90deg, #F2F3F5 25%, #E5E6EB 37%, #F2F3F5 63%)`, `background-size: 400% 100%`, moving for `1500ms cubic-bezier(0,0,1,1)`.
- Page wash, when needed: one broad corner wash `radial-gradient(circle at 20% 0%, rgba(0,149,104,.04), transparent 64%)`; it must not read as a discrete orb.

Forbidden: cross-hue gradients, large saturated fields, gradient text, decorative blobs/orbs, and gradients that reduce image inspectability.

## 5. Radius, Shadow, And Border

Arco's official family is none `0`, small `2px`, medium `4px`, large `8px`, and circle `50%`. Arco Button/Input/Card default to `2px`. PicGen mapping follows the implementation contract: button/input `4px`, scenario/card/modal `8px`, tiny status primitives `2px`, circle markers `50%`.

Official shadows:

| Token | Value | PicGen use |
|---|---|---|
| Special | `0 0 1px rgba(0,0,0,.3)` | crisp overlay edge only |
| Shadow 1 | `0 2px 5px rgba(0,0,0,.1)` | compact floating control |
| Shadow 2 | `0 4px 10px rgba(0,0,0,.1)` | card hover, Message, Tooltip |
| Shadow 3 | `0 8px 20px rgba(0,0,0,.1)` | modal/dialog |
| PicGen card rest | `0 1px 2px rgba(0,0,0,.06)` | scenario card at rest |

Every standard outline is `1px solid`. Normal uses `border-2 #E5E6EB`, hover uses `border-3 #C9CDD4` or primary level 4 for selectable cards, and active/selected uses primary level 6. Focus uses a `2px` outer ring in primary level 2; this is an intentional visible-focus adaptation because the current Arco Input token expands to a zero-spread shadow.

## 6. Spacing And Layout Rhythm

Official spacing values include `2, 4, 6, 8, 10, 12, 16, 20, 24, 32, 36, 40, 48, 56, 60, 64, 72, 80, 84, 96, 100, 120px`. Product layout uses a 4px base; `2/6/10px` are restricted to optical alignment and official component internals.

| Relationship | Value |
|---|---|
| icon to label | `8px` default, `4px` compact |
| label to input | `6px` |
| form item vertical gap | `16px` |
| related controls | `8px` or `12px` |
| card body padding | `16px` |
| field group gap | `24px` |
| major section gap | `32px` |
| desktop content inset | `32px` |
| mobile content inset | `16px` |

Arco Divider is `1px solid #E5E6EB`, with `20px` top/bottom margin. Labelled dividers use `14px/500`, `0 16px` label padding, and fixed `24px` end lines. Vertical Divider is `1px × 1em` with `12px` horizontal margins.

## 7. Component Anatomy

### Scene card / Card

Official Card: white background, `1px #E5E6EB`, `2px` radius, default body `16px`, header `46px`, title `16px/500`, body `14px`, and hover shadow `0 4px 10px rgb(gray-2)` with `200ms linear`; it has no built-in lift. PicGen scene card adapts to `8px` radius, `16:9` cover, `16px` body, rest shadow `0 1px 2px rgba(0,0,0,.06)`, and hover `translateY(-2px)`, primary-4 border, Shadow 2, `200ms standard/linear`. Active uses primary-6 border; keyboard focus adds the primary-2 ring. Loading replaces the cover/content with Skeleton; disabled uses text-4 and `opacity:.5`.

### Input and textarea

Official default Input is nominally `32px`, `14px/1.5715`, `4px 12px` padding, `1px transparent`, `2px` radius, text-1, placeholder text-3, and fill-2. Hover changes only to fill-3. Focus changes to white and primary-6 border. Disabled remains fill-2 with text/placeholder text-4. Color, border-color, and background-color transition for `100ms linear`.

PicGen changes radius to `4px` and adds a visible `0 0 0 2px` primary-2 focus ring. Error is danger-light default, danger level 2 hover, then white with danger-6 border on focus. Warning follows warning levels 1/2/6. Required validation text is `12px/20px` in danger-text.

### Radio.Button and Tag selection

Official Radio.Button group is fill-2, `32px` high, `1.5px` group padding/item margin, `12px` item horizontal padding, `2px` radius, `14px`; item hover is white/text-1 and checked is white/primary-6/weight 500. Focus is inset `0 0 0 2px primary-6`; transition is `100ms linear`. PicGen uses `4px` radius. Disabled is transparent/text-4; disabled selected is white/primary-3. Tag heights are `20/24/28/32px`, `0 8px`, `2px` radius, with `100ms linear` state transition.

### Steps

Circle markers are `28px` (`24px` small), icon `16px`, title `16px`, description `12px`, marker/title gap `12px`, and connector `1px #E5E6EB`. Wait uses fill-2/text-2, process uses primary-6 with white marker text, finish uses primary-1/primary-6 and primary-6 connector, error uses danger-6. PicGen's first-run checklist uses these values and a `300ms overshoot` check scale only when a step first completes.

### Skeleton

Image blocks are `48px` default (`36/60px` small/large), `2px` radius, with `16px` content gap. Text line height and line gap are both `16px`. Base is fill-2, highlight fill-3, exact stops `25/37/63%`, size `400% 100%`, duration `1500ms linear infinite`. Cards may adapt block radius to `4px`.

### Alert

Official Alert has `1px` transparent border, visual padding `8px 15px` (source token `9px 16px` before border subtraction), `2px` radius, `14px` body, `16px` title, and `16/18px` icons. PicGen maps radius to `4px`. Info/success/warning/error backgrounds are `#E8F3FF/#E8FFEA/#FFF7E8/#FFECE8`; icons use semantic level 6; no-title text uses text-1, titled detail uses text-2. Close icon is `12px`. No shadow.

### Message

Message uses `10px 16px`, `1px #E5E6EB`, `2px` official radius (PicGen `4px`), white background, text-1, semantic `16px` icon, Shadow 2, and `16px` stack gap. Enter is opacity/translate for `100-200ms standard`; exit is at most `300ms standard`. Auto-close remains the existing application behavior; Arco's default reference is `3000ms`.

### Buttons

Official default Button is `32px`, horizontal padding `15px`, `14px`, icon gap `8px`, weight `400`, `1px` border, `2px` radius, transition `all 100ms linear`, and no transition while active. PicGen radius is `4px`, label weight `500` for primary actions. Primary states are white on primary `6/5/7`, disabled white on primary-3, focus ring primary-2. Secondary is text-2 on fill `2/3/4`, disabled text-4 on fill-1. Text button is primary-6 on transparent/fill-2/fill-3. Loading freezes hover/active, shows the official `16px` loading icon, and rotates it `1000ms linear infinite`.

### Empty

Official Empty uses `10px 0`, `48px` icon or `80px` image, `4px` icon gap, `14px` description, and gray-5. PicGen uses a compact line illustration at approximately `120×78px`, currentColor gray-5, `2px` strokes, then a `14px/500` title and a `13px/20px` action-oriented sentence. An empty state may not be only a gray sentence.

### Spin, Badge, Tooltip, and Divider

- Spin: `20px` icon, primary-6, optional `14px/500` tip at `6px` gap, rotating `1000ms linear infinite`; overlay is white at `60%` opacity.
- Badge: count `20px` high/min-width, `0 6px`, `12px`, `20px` radius; dot `6×6px`; danger-6 background/white text; `0 0 0 2px` white edge. Status text has `8px` gap and `14px` type.
- Tooltip: `8px 12px` (`4px 12px` mini), `14px/1.5715`, `2px` radius, text white, background text-1, Shadow 2, max width `350px`, `8×8px` arrow, `200ms` zoom/fade reference. New icon-only tools always receive a tooltip.
- Divider follows the values in section 6 and has no radius, shadow, or animation.

## 8. State Matrix

| Control | Default | Hover | Active | Focus | Disabled | Loading |
|---|---|---|---|---|---|---|
| Primary button | white, primary-6 gradient | solid primary-5 | solid primary-7, transition none | primary-2 `2px` ring | white/primary-3, no pointer | default color, `16px` spinner, interactions locked |
| Secondary button | text-2/fill-2 | fill-3 | fill-4, transition none | neutral-4 `2px` ring | text-4/fill-1 | default color, spinner, interactions locked |
| Text button/link | primary-6/transparent | primary-6/fill-2; link level 5 | primary-6/fill-3; link level 7 | primary-2 or link level 2 ring | text-4/transparent | label retained plus spinner |
| Input | text-1/fill-2/transparent border | fill-3 | white/primary-7 after pointer focus | white/primary-6 border + primary-2 ring | text-4/fill-2, not-allowed | read-only fill-2 plus trailing spinner |
| Scene card | white/border-2/rest shadow | `-2px`, primary-4, Shadow 2 | primary-6 border, no extra lift | primary-2 ring | `.5` opacity, text-4, no pointer | cover/body Skeleton |
| Radio.Button | fill-2 group, transparent item/text-2 | white/text-1 | selected white/primary-6/500 | inset primary-6 `2px` | transparent/text-4; selected primary-3 | selection frozen; no separate spinner |

Hover selectors are suppressed on disabled and loading controls. `aria-busy`, `aria-disabled`, native `disabled`, visible focus, and stable dimensions are required; loading labels may not resize their parent.

## 9. Motion

Official duration tokens are `100ms`, `200ms`, `300ms`, `400ms`, `500ms`, and loading `1000ms`. Curves are:

- linear: `cubic-bezier(0,0,1,1)`
- standard: `cubic-bezier(0.34,0.69,0.1,1)`
- overshoot: `cubic-bezier(0.3,1.3,0.3,1)`
- decelerate: `cubic-bezier(0.4,0.8,0.74,1)`
- accelerate: `cubic-bezier(0.26,0,0.6,0.2)`

PicGen assignments: control hover `100ms linear`; card hover `200ms standard` transform plus `200ms linear` border/shadow; modal `200ms standard` opacity and scale `.96→1`; Message enter `200ms standard` with `translateY(-8px)→0`; completed Step check `300ms overshoot`; Skeleton `1500ms linear infinite`; Spin `1000ms linear infinite`. A single transition may not exceed `300ms`; loading loops are the explicit exception. There is no staggered entrance choreography.

Under `@media (prefers-reduced-motion: reduce)`, new UI animation/transition durations become `0.01ms`, iteration count becomes `1`, smooth scrolling is disabled, and transforms settle at their final position. Information must remain visible without motion.

## 10. Explicit Exclusions

- Do not use Arco blue as PicGen's primary; blue remains only link/info semantics.
- Do not implement dark mode in this release.
- Do not import Arco packages, JS behavior, CSS bundles, or a frontend build step at runtime.
- Do not add large illustration packs; Empty uses a small local line illustration.
- Do not reproduce dropdown/modal mechanics from the component library; existing PicGen behavior remains authoritative.
- Do not use cross-hue gradients, decorative orbs, gradient text, excessive elevation, or staged entrance animation.
- Do not restyle the professional workspace. Its only visual addition is the mode-switch control required by the task.

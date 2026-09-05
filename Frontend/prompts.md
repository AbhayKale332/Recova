# Character art prompts — Meena & Shashank

Image-generation prompts for the two characters in the landing-page story
(`src/components/story/`). Until these are added, each character renders a
built-in SVG placeholder, so the scroll already works — dropping the PNGs in
replaces the placeholder with no code change.

## Where the files go

| Character | Folder | Filenames |
|-----------|--------|-----------|
| Meena     | `public/meena/`     | `meena-wave.png`, `meena-worried.png`, `meena-confused.png`, `meena-facepalm.png`, `meena-hips.png`, `meena-tired.png`, `meena-hopeful.png` |
| Shashank  | `public/shashank/`  | `shashank-wave.png`, `shashank-worried.png`, `shashank-confused.png`, `shashank-facepalm.png`, `shashank-hips.png`, `shashank-tired.png`, `shashank-hopeful.png` |

Seven poses per character (the `hips` pose is not currently used in the script
but the loader expects the file — generate it for completeness).

## Shared style (paste into every prompt)

> Flat vector character illustration in the style of humaaans.com / Clay
> illustrations. Single full-body figure, head to feet, standing, feet flat on
> an invisible ground line at the very bottom edge of the frame. Clean geometric
> shapes, subtle grain-free flat shading, no outlines or thin consistent
> outlines only. Friendly, calm, modern startup aesthetic. Transparent
> background (PNG with alpha). Portrait framing roughly 1000×1400. The figure is
> centered horizontally with a little headroom. Muted palette with a single
> blue accent (#1a56db). No text, no logos, no props floating in the air, no
> drop shadow on the background. Same character, same face, same outfit, same
> proportions across every pose — this is one image from a character sheet.

Generate a **character sheet / reference image first** (front-facing neutral
stance) for each person, then use it as an image reference/seed for all seven
poses so the face and outfit stay identical.

---

## Meena

**Base character:**

> Meena — an Indian woman in her early 30s, warm and grounded, runs a tiny
> three-person home-décor label from Pune. Medium-brown skin, dark brown hair
> in a low bun with a few loose strands, small gold stud earrings. Wearing a
> terracotta / clay-orange cotton kurta over slim indigo trousers, flat
> sandals, a thin cloth crossbody bag. Approachable, a little tired around the
> eyes but determined. Body type average, relaxed posture.

| Pose file | Story beat | Prompt (append to Base + Shared style) |
|-----------|-----------|----------------------------------------|
| `meena-wave` | "Hi. I'm Meena." | Standing relaxed, one hand raised in a small friendly wave near her shoulder, slight warm smile, weight on one leg. |
| `meena-worried` | A cart was abandoned, no error | Standing, arms loosely crossed, looking slightly down and to the side, brow gently furrowed, worried but composed. |
| `meena-confused` | A card keeps getting declined | Standing, one hand on her chin / cheek, head tilted, the other arm across her body, puzzled expression, looking off-frame as if re-reading something. *(Rendered wider in the layout — full body still, but she can be turned 3/4.)* |
| `meena-facepalm` | A renewal quietly failed for weeks | Standing, one palm pressed to her forehead, eyes closed, other hand on hip, exasperated but not dramatic. |
| `meena-hips` | (unused spare) | Standing confidently, both hands on hips, chin up, steady and matter-of-fact. |
| `meena-tired` | An invoice went 46 days overdue while she slept | Standing, shoulders dropped, one hand rubbing the back of her neck, holding a phone loosely in the other hand, drained, end-of-a-long-day energy. |
| `meena-hopeful` | "I can't be the only one." | Standing straighter, looking up and slightly forward, a small hopeful half-smile, hands open at her sides or one hand lightly over her heart. |

---

## Shashank

**Base character:**

> Shashank — an Indian man in his late 30s, head of revenue operations at a
> mid-to-large SaaS company. Medium-brown skin, short neat black hair, trimmed
> stubble, thin dark rectangular glasses. Wearing a deep blue (#1a56db)
> button-down shirt, sleeves rolled to the forearm, over charcoal chinos, dark
> loafers, and a company lanyard with a blank white ID badge. Sharp but
> stretched-thin; carries himself like someone who has been in back-to-back
> meetings. Body type average, upright corporate posture.

| Pose file | Story beat | Prompt (append to Base + Shared style) |
|-----------|-----------|----------------------------------------|
| `shashank-wave` | (spare / alt intro) | Standing relaxed, one hand raised in a brief professional wave, polite half-smile. |
| `shashank-worried` | CEO keeps asking "where is the money going?" | Standing, one hand pinching the bridge of his nose under his glasses, other hand holding a rolled report or tablet at his side, tense, under pressure. |
| `shashank-confused` | "It was Meena's four leaks — at a thousand times the volume." | Standing 3/4 turned, both hands slightly raised and open in a "how did we miss this" gesture, looking at an invisible dashboard off-frame, disbelief. *(Rendered wider in the layout.)* |
| `shashank-facepalm` | (spare) | Standing, one hand covering his eyes, glasses pushed up onto his forehead, other hand on hip, quiet frustration. |
| `shashank-hips` | "I'm Shashank — I run revenue operations." | Standing squarely, both hands on hips, chin level, confident and direct — this is his introduction pose. |
| `shashank-tired` | Six analysts, a wall of dashboards, still can't say which payments to chase | Standing, shoulders slumped, loosening or holding his collar with one hand, other hand holding a coffee cup, worn down, late-night-at-the-office energy. |
| `shashank-hopeful` | "One kitchen table or one boardroom — the leak is the same shape." | Standing tall, arms relaxed, looking forward with a calm, resolved expression, a slight optimistic lift to his posture — the turn toward a solution. |

---

## Consistency checklist

- Same face, hair, skin tone, glasses (Shashank), and outfit in all seven poses per character.
- Feet on the bottom edge; transparent background; no shadow baked onto the alpha.
- Keep the two characters visually distinct: Meena = clay/terracotta kurta, warm; Shashank = blue shirt + lanyard, corporate.
- Export as PNG with alpha, roughly 1000×1400, trimmed so the figure fills most of the height.
- `confused` and `hopeful` may be exported slightly wider — the loader up-scales them so they read at the same size as the rest.

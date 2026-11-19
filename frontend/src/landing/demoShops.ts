/** S21: the demo shops on the landing strip. Same names and order as DEMOS in backend/app/sites/demo.py (a backend
 * test checks the slugs, names, looks and that each thumbnail exists and is small). Thumbnails are made by
 * scripts/make_demo_thumbs.js from the real demo pages. */
export type DemoShop = { slug: string; name: string; look: string; thumb: string };

export const DEMO_SHOPS: DemoShop[] = [
  { slug: "meera", name: "Meera's Eggless Bakes", look: "Bakery", thumb: "/demos/meera.webp" },
  { slug: "imran", name: "Sheikh Ladies & Gents Tailors", look: "Tailoring", thumb: "/demos/imran.webp" },
  { slug: "sunita", name: "Annapurna Ghar Ka Khana", look: "Home kitchen", thumb: "/demos/sunita.webp" },
  { slug: "sugarcrumb", name: "Sugar & Crumb Cake Studio", look: "Bakery", thumb: "/demos/sugarcrumb.webp" },
  { slug: "zari", name: "Zari & Thread Tailoring", look: "Tailoring", thumb: "/demos/zari.webp" },
  { slug: "ember", name: "Ember & Clay Candles", look: "Handmade", thumb: "/demos/ember.webp" },
  { slug: "giftgarden", name: "Gift Garden Hampers", look: "Gifts", thumb: "/demos/giftgarden.webp" },
  { slug: "greencorner", name: "Green Corner Nursery", look: "General", thumb: "/demos/greencorner.webp" },
];

/** Thumbnail size (the files are 390 x 780, the first screen of each demo on a phone). */
export const THUMB_W = 390;
export const THUMB_H = 780;

import { ref } from "vue";

/**
 * Per-route document title, `<meta>` description and Open Graph tags.
 *
 * Vue Router is history-based, so without this every route shares the one
 * `<title>` baked into `index.html`, and a link pasted into chat/social has no
 * useful preview. `setDocumentTitle` updates the tab title and the OG/Twitter
 * meta tags client-side; static routes set it from `route.meta.title` (see the
 * router `afterEach`) and dynamic pages (a package, a shared link) refine it
 * once their data loads.
 *
 * NOTE: this is client-side only. Crawlers that execute JavaScript see the
 * updated tags, but many social scrapers read the initial HTML — true rich
 * previews for `/s/:token` still require server-side rendering/prerendering.
 * The shared `routeAnnouncement` ref additionally feeds an `aria-live` region
 * in `App.vue`, so assistive tech announces the new page after a client-side
 * navigation (which otherwise produces no announcement).
 */
const BASE_TITLE = "EasyShare";
const DEFAULT_DESCRIPTION = "Secure file and package sharing.";

/** The current page label, announced politely to assistive technology. */
export const routeAnnouncement = ref("");

function upsertMeta(key: string, value: string, useProperty = false): void {
  const attr = useProperty ? "property" : "name";
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.append(el);
  }
  el.setAttribute("content", value);
}

/**
 * Set the document title (and matching OG/Twitter tags) for the current view.
 * Pass no title to reset to the bare app name (e.g. the landing/login screen).
 */
export function setDocumentTitle(title?: string | null, description?: string): void {
  const label = title?.trim() || "";
  const full = label ? `${label} \u00b7 ${BASE_TITLE}` : BASE_TITLE;
  document.title = full;
  routeAnnouncement.value = label || BASE_TITLE;

  const desc = description?.trim() || DEFAULT_DESCRIPTION;
  upsertMeta("description", desc);
  upsertMeta("og:title", full, true);
  upsertMeta("og:description", desc, true);
  upsertMeta("og:type", "website", true);
  upsertMeta("twitter:card", "summary");
  upsertMeta("twitter:title", full);
  upsertMeta("twitter:description", desc);
}

// Review pages (the glyph sheet and the figure parts, visual spec 5.2) are
// built under this folder of dist/. They are not routes: the dist checks,
// the sitemap, llms.txt and search leave the folder out, and the deploy job
// removes it before publishing. No imports, so the check scripts can load it.
export const REVIEW_DIR = '_review';

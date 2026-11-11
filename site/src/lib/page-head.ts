// The <title> text and meta description of a Markdown page.
// - The description is the route's own, if it has one, else the one
//   remark-page-meta read from the Markdown.
// - A version of the Standard has the same H1 in every version, so its
//   <title> and description start from its Version line. Only the <title>
//   changes: the H1 on the page, and its id, stay as written.
import type { PageMeta } from '../plugins/remark-page-meta';
import { shortDescription } from '../plugins/remark-page-meta';
import type { Route } from './routes';

export interface PageHead {
  /** The page's own title, for the breadcrumb. */
  title: string;
  /** The <title> text before the site name. */
  headTitle: string;
  description: string | null;
}

export function pageHead(route: Route, page: PageMeta): PageHead {
  const title = page.title ?? route.title;
  const description = route.description ?? page.description;
  if (route.template === 'spec' && page.version) {
    return {
      title,
      headTitle: `${title}, version ${page.version}`,
      description: description === null ? null : shortDescription(`Version ${page.version}. ${description}`),
    };
  }
  return { title, headTitle: title, description };
}

/** A page's Markdown copy, with the title and description llms.txt lists it by. */
export interface Twin {
  title: string;
  description: string | null;
  markdown: string;
}

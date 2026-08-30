import { LegalLinksNav } from "./LegalLinksNav";

type LegalBlock =
  | {
      kind: "paragraphs";
      vi: readonly string[];
      en: readonly string[];
    }
  | {
      kind: "bullets";
      vi: readonly string[];
      en: readonly string[];
    };

type LegalSection = {
  heading: string;
  blocks: readonly LegalBlock[];
};

function LanguageBlock({
  heading,
  paragraphs,
}: {
  heading: string;
  paragraphs: readonly string[];
}) {
  return (
    <div className="legal-language-block">
      <h3>{heading}</h3>
      {paragraphs.map((paragraph) => (
        <p key={`${heading}-${paragraph.slice(0, 24)}`}>{paragraph}</p>
      ))}
    </div>
  );
}

function LanguageList({
  heading,
  items,
}: {
  heading: string;
  items: readonly string[];
}) {
  return (
    <div className="legal-language-block">
      <h3>{heading}</h3>
      <ul>
        {items.map((item) => (
          <li key={`${heading}-${item.slice(0, 24)}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function PublicLegalPage({
  title,
  subtitle,
  effectiveDate,
  updatedDate,
  sections,
}: {
  title: string;
  subtitle: string;
  effectiveDate: string;
  updatedDate: string;
  sections: readonly LegalSection[];
}) {
  return (
    <section className="page-section legal-page legal-page-scroll">
      <article className="legal-article">
        <header className="legal-header">
          <p className="eyebrow">GXP QLCL</p>
          <h1>{title}</h1>
          <p className="legal-subtitle">{subtitle}</p>
          <dl className="legal-meta">
            <div>
              <dt>Effective date / Ngày hiệu lực</dt>
              <dd>{effectiveDate}</dd>
            </div>
            <div>
              <dt>Last updated / Cập nhật lần cuối</dt>
              <dd>{updatedDate}</dd>
            </div>
          </dl>
        </header>

        <div className="legal-content">
          {sections.map((section) => (
            <section className="legal-section" key={section.heading}>
              <h2>{section.heading}</h2>
              {section.blocks.map((block, index) =>
                block.kind === "paragraphs" ? (
                  <div className="legal-language-grid" key={`${section.heading}-${index}`}>
                    <LanguageBlock heading="Tiếng Việt" paragraphs={block.vi} />
                    <LanguageBlock heading="English" paragraphs={block.en} />
                  </div>
                ) : (
                  <div className="legal-language-grid" key={`${section.heading}-${index}`}>
                    <LanguageList heading="Tiếng Việt" items={block.vi} />
                    <LanguageList heading="English" items={block.en} />
                  </div>
                ),
              )}
            </section>
          ))}
        </div>

        <footer className="legal-footer">
          <LegalLinksNav ariaLabel="Legal page navigation" className="legal-links legal-links-footer" />
        </footer>
      </article>
    </section>
  );
}

import { moduleLoaderText } from '../../config/neuroConstants.js';

export default function ModuleLoader({ tabId }) {
  const content = moduleLoaderText[tabId] || moduleLoaderText.overview;

  return (
    <section className={`product-card loading-card module-loader module-loader-${tabId}`} aria-live="polite">
      <div className="module-loader-visual" aria-hidden="true">
        {tabId === 'overview' ? (
          <>
            <span className="module-brain-core" />
            <span className="module-brain-fold fold-one" />
            <span className="module-brain-fold fold-two" />
            <span className="module-scan-axis" />
          </>
        ) : null}
        {tabId === 'pipeline' ? (
          <div className="pipeline-loader">
            <span />
            <span />
            <span />
            <span />
          </div>
        ) : null}
        {tabId === 'biopsy' ? (
          <div className="dna-loader">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        ) : null}
        {tabId === 'xai' ? (
          <div className="heat-loader">
            {Array.from({ length: 16 }, (_, index) => (
              <span key={index} />
            ))}
          </div>
        ) : null}
        {tabId === 'report' ? (
          <div className="report-loader">
            <span />
            <span />
            <span />
            <span />
          </div>
        ) : null}
        {tabId === 'fhir' ? (
          <div className="fhir-loader">
            <span className="node-a" />
            <span className="node-b" />
            <span className="node-c" />
            <span className="node-d" />
          </div>
        ) : null}
      </div>
      <div className="loader-copy">
        <span>{content.eyebrow}</span>
        <strong>{content.title}</strong>
        <small>{content.detail}</small>
      </div>
      <div className="loader-steps" aria-label="Modül geçiş adımları">
        <i />
        <i />
        <i />
      </div>
    </section>
  );
}

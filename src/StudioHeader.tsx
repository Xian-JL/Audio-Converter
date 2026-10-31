import { version } from '../package.json';

export default function StudioHeader({ language, onLanguage, ready, title, subtitle }: {
  language: 'en' | 'zh'; onLanguage: (language: 'en' | 'zh') => void;
  ready: boolean; title: string; subtitle: string;
}) {
  return <header className="site-header">
    <a className="brand" href="#" aria-label={title}>
      <span className="brand-icon" aria-hidden="true">♫</span>
      <span>{title}<small>{subtitle}</small></span>
      <span className="release-tag">v{version}</span>
    </a>
    <div className="header-controls">
      <span className={`service-indicator ${ready ? 'ready' : ''}`} role="status">
        <i aria-hidden="true" />{language === 'zh' ? (ready ? '本机服务已就绪' : '正在连接本机服务') : (ready ? 'Local service ready' : 'Connecting to local service')}
      </span>
      <div className="language" aria-label="Language / 语言">
        <button className={language === 'en' ? 'active' : ''} aria-pressed={language === 'en'} onClick={() => onLanguage('en')}>EN</button>
        <button className={language === 'zh' ? 'active' : ''} aria-pressed={language === 'zh'} onClick={() => onLanguage('zh')}>中文</button>
      </div>
    </div>
  </header>;
}

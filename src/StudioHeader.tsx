import { version } from '../package.json';

export default function StudioHeader({language,onLanguage,status,ready,title}:{
  language:'en'|'zh'; onLanguage:(language:'en'|'zh')=>void; status:string; ready:boolean; title:string;
}) {
  return <header className="site-header">
    <div className="brand"><img className="brand-icon" src="/favicon.ico" width="32" height="32" alt="" />{title}</div>
    <div className="header-controls">
      <span className={`service-indicator ${ready?'ready':''}`} role="status"><i aria-hidden="true"/>{status}</span>
      <details className="about-studio"><summary>{language==='zh'?'关于':'About'}</summary><span>v{version}</span></details>
      <div className="language" aria-label="Language / 语言">
        <button className={language==='en'?'active':''} aria-pressed={language==='en'} onClick={()=>onLanguage('en')}>EN</button>
        <button className={language==='zh'?'active':''} aria-pressed={language==='zh'} onClick={()=>onLanguage('zh')}>中文</button>
      </div>
    </div>
  </header>;
}

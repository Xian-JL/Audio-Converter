import { useId } from 'react';
import type { ReactNode } from 'react';

export type ToolTab = 'melody' | 'harmony' | 'instrumental' | 'sound' | 'export';
const tabs: ToolTab[] = ['melody', 'harmony', 'instrumental', 'sound', 'export'];
const labels = {
  zh: ['旋律', '和弦', '器乐', '演奏', '导出'],
  en: ['Melody', 'Chords', 'Compose', 'Sound', 'Export'],
};

/** Keep every panel mounted: changing tasks must not cancel a generation or lose a draft. */
export default function ToolWorkspace({ language, active, onChange, panels }: {
  language: 'en' | 'zh';
  active: ToolTab;
  onChange: (tab: ToolTab) => void;
  panels: Record<ToolTab, ReactNode>;
}) {
  const id = useId();
  return <div className="task-workspace">
    <div className="tool-tabs" role="tablist" aria-label={language === 'zh' ? '工作任务' : 'Workspace tasks'}
      onKeyDown={event => {
        const index = tabs.indexOf(active);
        const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length
          : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
          : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1;
        if (next < 0) return;
        event.preventDefault();
        onChange(tabs[next]);
        event.currentTarget.querySelectorAll<HTMLButtonElement>('[role=tab]')[next]?.focus();
      }}>
      {tabs.map((tab, index) => <button key={tab} type="button" role="tab" id={`${id}-${tab}-tab`}
        aria-controls={`${id}-${tab}-panel`} aria-selected={active === tab} tabIndex={active === tab ? 0 : -1}
        onClick={() => onChange(tab)}>{labels[language][index]}</button>)}
    </div>
    {tabs.map(tab => <div key={tab} className="tool-task" role="tabpanel" tabIndex={0}
      id={`${id}-${tab}-panel`} aria-labelledby={`${id}-${tab}-tab`} hidden={active !== tab}>
      {panels[tab]}
    </div>)}
  </div>;
}

import Markdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import type { AssistantMessageItem } from '../types/snapshot';
import styles from './Cards.module.css';
import { MessageTime } from './MessageTime';

/** 助手流式文本（票 13 / 14）：Markdown 经 sanitize 渲染，脚本标签被剥离；fallback 标「简化回复」；aborted 显示中断。 */
export function AssistantBubble({ item }: { item: AssistantMessageItem }) {
  return (
    <div className={styles.assistantRow} data-status={item.status} data-testid="assistant-bubble">
      <span className={styles.avatar} aria-hidden="true">✦</span>
      <div className={styles.assistantBubble}>
        {item.model_tier === 'fallback' && <span className={styles.tierTag} title="主模型不可用，由备用模型生成">简化回复</span>}
        <div className={styles.markdown}>
          <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} disallowedElements={['script', 'iframe', 'style']} unwrapDisallowed>
            {item.text}
          </Markdown>
        </div>
        {item.status === 'streaming' && <span className={styles.cursor} aria-label="正在输入" />}
        {item.status === 'aborted' && <p className={styles.abortNote}>这段回复中断了，正在换用备用方式重新生成…</p>}
        {item.status === 'replaced' && <p className={styles.abortNote}>此回复已被后续答复替换</p>}
        <MessageTime at={item.at} />
      </div>
    </div>
  );
}

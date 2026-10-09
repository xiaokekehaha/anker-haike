import Markdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import type { AssistantMessageItem } from '../types/snapshot';
import styles from './Cards.module.css';

/** 助手流式文本（票 13 / 14）：Markdown 经 sanitize 渲染，脚本标签被剥离；fallback 标「简化回复」；aborted 显示中断。
 *  cont：紧接上一条助手消息，头像占位但不显示，避免连续回复堆一列头像。 */
export function AssistantBubble({ item, cont = false }: { item: AssistantMessageItem; cont?: boolean }) {
  return (
    <div className={styles.assistantRow} data-status={item.status} data-testid="assistant-bubble">
      <span className={styles.avatar} data-ghost={cont || undefined} aria-hidden="true">✦</span>
      <div className={styles.assistantBubble}>
        {item.model_tier === 'fallback' && <span className={styles.tierTag} title="主模型不可用，由备用模型生成">简化回复</span>}
        <div className={styles.markdown}>
          <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} disallowedElements={['script', 'iframe', 'style']} unwrapDisallowed>
            {item.text}
          </Markdown>
        </div>
        {item.status === 'streaming' && <span className={styles.cursor} aria-label="正在输入" />}
        {item.status === 'aborted' && <p className={styles.abortNote} role="status">这段回复没有完成，上面的内容不完整，请以后续说明为准。</p>}
        {item.status === 'replaced' && <p className={styles.abortNote}>此回复已被后续答复替换</p>}
      </div>
    </div>
  );
}

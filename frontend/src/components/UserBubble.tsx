import { imageUrl } from '../lib/image';
import styles from './UserBubble.module.css';

type ImageRef = { image_id: string; purpose?: 'fault' | 'receipt' };
type Props = { sessionId: string; text: string; images?: ImageRef[]; imageIds?: string[] };

/** 用户消息气泡（票 29）：文字 + 缩略图；缩略图从会话内图片接口取，1 小时后清理即失效。 */
export function UserBubble({ sessionId, text, images, imageIds }: Props) {
  const refs: ImageRef[] = images && images.length > 0 ? images : (imageIds ?? []).map((id) => ({ image_id: id }));
  return (
    <div className={styles.row}>
      <div className={styles.bubble}>
        {text && <p className={styles.text}>{text}</p>}
        {refs.length > 0 && (
          <ul className={styles.thumbs} aria-label="附带图片">
            {refs.map((r, i) => (
              <li key={r.image_id}>
                <img
                  src={imageUrl(sessionId, r.image_id)}
                  alt={r.purpose === 'receipt' ? `购买凭证 ${i + 1}` : `故障图片 ${i + 1}`}
                  loading="lazy"
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** DAG：静态拓扑做底图，按阶段分列自动布局（阶段本身就是有意义的泳道，比通用分层更好读）。
 *
 *  三种用法共用一套渲染：
 *  - path：单次 run 实际走过的节点，高亮并标顺序号，其余置灰（dataviz 的「强调」形式）；
 *  - traffic：聚合流量，边宽 = 经过次数，节点底色深浅 = 经过次数（单色顺序标度）；
 *  - 两者都没有：纯拓扑。
 */
import { useCallback, useMemo } from 'react';
import { Background, Controls, Position, ReactFlow, type Edge, type Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { nodeLabel } from '../format';
import type { Flow, Topology } from '../types';

const COL_W = 132;
const ROW_H = 52;

/** 单色蓝顺序标度：0 → 最浅，1 → 最深。离散档位，最浅一档仍能看清。 */
const BLUE = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#2a78d6', '#1c5cab'];

function shade(ratio: number): string {
  const step = Math.min(BLUE.length - 1, Math.max(0, Math.round(ratio * (BLUE.length - 1))));
  return BLUE[step] ?? BLUE[BLUE.length - 1]!;
}

export type GraphMode = { path?: string[]; traffic?: Flow | null };

export function GraphView({ topology, path, traffic, onSelect, selected, small }: {
  topology: Topology;
  path?: string[];
  traffic?: Flow | null;
  onSelect?: (node: string) => void;
  selected?: string | null;
  small?: boolean;
}) {
  const onPath = useMemo(() => new Set(path ?? []), [path]);
  // 节点在路径中的出现次序（同一节点可能被走过多次，标第一次的序号）
  const order = useMemo(() => {
    const map = new Map<string, number>();
    (path ?? []).forEach((node, i) => { if (!map.has(node)) map.set(node, i + 1); });
    return map;
  }, [path]);

  const trafficByNode = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of traffic?.nodes ?? []) map.set(row.node, row.n);
    return map;
  }, [traffic]);
  const maxNodeTraffic = Math.max(1, ...trafficByNode.values());

  const nodes: Node[] = useMemo(() => {
    // 按阶段分列；列内按拓扑里的出现顺序堆叠
    const columns = new Map<string, string[]>();
    for (const node of topology.nodes) {
      const list = columns.get(node.stage) ?? [];
      list.push(node.id);
      columns.set(node.stage, list);
    }
    const stages = topology.stage_order.filter((stage) => columns.has(stage));
    const tallest = Math.max(...stages.map((stage) => columns.get(stage)!.length));
    return topology.nodes.map((node) => {
      const column = stages.indexOf(node.stage);
      const list = columns.get(node.stage)!;
      const row = list.indexOf(node.id);
      const offset = (tallest - list.length) / 2;
      const hit = onPath.has(node.id);
      const seq = order.get(node.id);
      const n = trafficByNode.get(node.id) ?? 0;
      const dim = (path && path.length > 0 && !hit) || (!!traffic && n === 0);
      return {
        id: node.id,
        position: { x: column * COL_W, y: (row + offset) * ROW_H },
        data: {
          label: (
            <div className="dagnode" data-on={hit || undefined} data-dim={dim || undefined}
              style={traffic && n > 0 && !path ? { background: shade(n / maxNodeTraffic), borderColor: 'transparent', color: n / maxNodeTraffic > 0.55 ? '#fff' : '#0b0b0b' } : undefined}>
              {seq !== undefined && <span className="seq">{seq}</span>}
              {nodeLabel(node.id)}
              {traffic && n > 0 && <span className="n" style={n / maxNodeTraffic > 0.55 ? { color: '#ffffffcc' } : undefined}>{n} 次</span>}
            </div>
          ),
        },
        style: {
          background: 'transparent', border: 'none', padding: 0, width: 'auto',
          outline: selected === node.id ? '2px solid var(--accent)' : undefined,
          outlineOffset: 3, borderRadius: 10,
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });
  }, [topology, onPath, order, trafficByNode, maxNodeTraffic, traffic, path, selected]);

  const edges: Edge[] = useMemo(() => {
    const counts = new Map<string, number>();
    for (const edge of traffic?.edges ?? []) counts.set(`${edge.source}->${edge.target}`, edge.n);
    const maxEdge = Math.max(1, ...counts.values());
    // 路径里相邻出现过的边
    const walked = new Set<string>();
    for (let i = 1; i < (path?.length ?? 0); i += 1) walked.add(`${path![i - 1]}->${path![i]}`);
    return topology.edges.map((edge) => {
      const key = `${edge.source}->${edge.target}`;
      const n = counts.get(key) ?? 0;
      const hit = walked.has(key);
      const width = traffic && !path ? 1 + (n / maxEdge) * 7 : hit ? 2.5 : 1;
      return {
        id: key,
        source: edge.source,
        target: edge.target,
        animated: hit,
        label: traffic && !path && n > 0 ? String(n) : undefined,
        labelStyle: { fontSize: 10, fill: 'var(--muted)' },
        labelBgStyle: { fill: 'var(--surface)' },
        style: {
          stroke: hit ? 'var(--accent)' : n > 0 ? 'var(--viz-series-1)' : 'var(--border)',
          strokeWidth: width,
          strokeDasharray: edge.conditional && !hit ? '4 3' : undefined,
          opacity: (path && path.length > 0 && !hit) || (!!traffic && n === 0) ? 0.3 : 1,
        },
      };
    });
  }, [topology, traffic, path]);

  const handleClick = useCallback(
    (_: unknown, node: Node) => onSelect?.(node.id),
    [onSelect],
  );

  return (
    <div className={small ? 'dag dag-sm' : 'dag'}>
      <ReactFlow nodes={nodes} edges={edges} onNodeClick={handleClick}
        fitView fitViewOptions={{ padding: 0.12, minZoom: 0.4 }}
        nodesDraggable={false} nodesConnectable={false} minZoom={0.35} maxZoom={1.8}>
        <Background color="var(--viz-grid)" gap={22} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

/** DAG：静态拓扑做底图。
 *
 *  三种用法共用一套渲染：
 *  - path：单次 run 实际走过的节点，高亮并标顺序号，其余置灰（dataviz 的「强调」形式）；
 *  - traffic：聚合流量，边宽 = 经过次数，节点底色深浅 = 经过次数（单色顺序标度）；
 *  - 两者都没有：纯拓扑。
 *
 *  布局：有流量时按实际先后分列（见 layoutBySteps）；没有流量时按阶段分列。
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

type Layout = { columns: string[][]; columnOf: Map<string, number> };

function toLayout(columnOf: Map<string, number>, ids: string[]): Layout {
  const columns: string[][] = [];
  for (const id of ids) (columns[columnOf.get(id)!] ??= []).push(id);
  // 跳过空列，列号压紧
  const kept = columns.filter((list) => list && list.length > 0);
  const compact = new Map<string, number>();
  kept.forEach((list, i) => list.forEach((id) => compact.set(id, i)));
  return { columns: kept, columnOf: compact };
}

/** 没有流量数据时（单次 run 的路径视图、纯拓扑）：按阶段分列，列内按拓扑出现顺序。 */
function layoutByStage(topology: Topology): Layout {
  const stages = topology.stage_order.filter((stage) => topology.nodes.some((node) => node.stage === stage));
  const columnOf = new Map(topology.nodes.map((node) => [node.id, Math.max(0, stages.indexOf(node.stage))]));
  return toLayout(columnOf, topology.nodes.map((node) => node.id));
}

/** 按实际先后分列。
 *
 *  每个节点的排序键 = 它在一轮里的平均步序（node_runs.idx 的均值）。只有「键更小 → 键更大」的边算前进边，
 *  其余（如 读图 → 产品消歧、升级后回到核实服务信息）是回跳，不参与排序；键是全序，前进边必然无环。
 *  列号 = 沿前进边从开始到该节点的最长路径，保证每条前进边都从左指向右。
 *  窗口内没走过的节点没有步序：取其已知上游与下游键的中点，只是为了有个位置，画出来是置灰的。
 *  列内按经过次数从多到少排。
 */
function layoutBySteps(topology: Topology, steps: Map<string, number>, traffic: Map<string, number>): Layout {
  const ids = topology.nodes.map((node) => node.id);
  const key = new Map<string, number>(steps);
  key.set('__start__', 0);
  key.set('__end__', Number.MAX_SAFE_INTEGER);
  for (const id of ids) {
    if (key.has(id)) continue;
    const before = topology.edges.filter((e) => e.target === id && steps.has(e.source)).map((e) => steps.get(e.source)!);
    const after = topology.edges.filter((e) => e.source === id && steps.has(e.target)).map((e) => steps.get(e.target)!);
    const lo = before.length > 0 ? Math.max(...before) : null;
    const hi = after.length > 0 ? Math.min(...after) : null;
    key.set(id, lo !== null && hi !== null ? (lo + hi) / 2 : lo !== null ? lo + 0.5 : hi !== null ? hi - 0.5 : Number.MAX_SAFE_INTEGER - 1);
  }
  const preds = new Map<string, string[]>();
  for (const e of topology.edges) {
    if (key.get(e.source)! < key.get(e.target)!) preds.set(e.target, [...(preds.get(e.target) ?? []), e.source]);
  }
  const columnOf = new Map<string, number>();
  // 按键升序处理，前驱的列号必然先算好
  for (const id of [...ids].sort((a, b) => key.get(a)! - key.get(b)!)) {
    const before = preds.get(id) ?? [];
    columnOf.set(id, before.length === 0 ? 0 : 1 + Math.max(...before.map((p) => columnOf.get(p)!)));
  }
  const byTraffic = [...ids].sort((a, b) => (traffic.get(b) ?? 0) - (traffic.get(a) ?? 0));
  return toLayout(columnOf, byTraffic);
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

  const layout = useMemo(() => {
    const steps = new Map((traffic?.nodes ?? []).map((row) => [row.node, row.avg_step]));
    return steps.size > 0 ? layoutBySteps(topology, steps, trafficByNode) : layoutByStage(topology);
  }, [topology, traffic, trafficByNode]);

  const nodes: Node[] = useMemo(() => {
    const tallest = Math.max(...layout.columns.map((list) => list.length));
    return topology.nodes.map((node) => {
      const column = layout.columnOf.get(node.id)!;
      const list = layout.columns[column]!;
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
  }, [topology, layout, onPath, order, trafficByNode, maxNodeTraffic, traffic, path, selected]);

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

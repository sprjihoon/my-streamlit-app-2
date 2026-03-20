'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  getPrepackingVendors,
  analyzePrepackingCombos,
  predictPrepacking,
  getDailyInstructions,
  createPrepackingProduction,
  getActiveProductions,
  usePrepackingProduction,
  updatePrepackingStatus,
  updatePrepackingLocation,
  getAccuracyHistory,
  getPrepackingEfficiency,
  updatePrepackingAccuracy,
  getAllPrepackingSettings,
  savePrepackingSettings,
  suggestLocations,
  debugPrepackingSampleRows,
  type PrepackingCombo,
  type PrepackingPrediction,
  type PrepackingProduction,
  type DailyInstructions,
  type PrepackingSettings,
  type AccuracyRecord,
  type EfficiencyStats,
  type ComboDetail,
} from '@/lib/api';

/* ── 상수 ── */
const WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일'];
const STATUS_MAP: Record<string, { label: string; color: string; bg: string }> = {
  active:       { label: '사용가능',   color: '#16a34a', bg: '#f0fdf4' },
  carried:      { label: '이월',       color: '#2563eb', bg: '#eff6ff' },
  held:         { label: '보류',       color: '#ca8a04', bg: '#fefce8' },
  disassemble:  { label: '해체지시',   color: '#dc2626', bg: '#fef2f2' },
  disassembled: { label: '해체완료',   color: '#6b7280', bg: '#f9fafb' },
  depleted:     { label: '소진',       color: '#9ca3af', bg: '#f9fafb' },
};

type Tab = 'instructions' | 'production' | 'inventory' | 'analysis' | 'accuracy' | 'settings';

/* ── 유틸 ── */
function parseDetail(s: string): ComboDetail[] { try { return JSON.parse(s); } catch { return []; } }
function fmtCombo(key: string) { return key.split('|').map(p => { const [n, q] = p.split(':'); return `${n} x${q}`; }).join(' + '); }
function today() { return new Date().toISOString().split('T')[0]; }
function tomorrow() { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().split('T')[0]; }
function weeksAgo(w: number) { const d = new Date(); d.setDate(d.getDate() - w * 7); return d.toISOString().split('T')[0]; }

/* ── 공통 컴포넌트 ── */
function Badge({ label, color, bg }: { label: string; color: string; bg: string }) {
  return <span style={{ padding: '2px 10px', borderRadius: 99, fontSize: 12, fontWeight: 600, color, backgroundColor: bg, whiteSpace: 'nowrap' }}>{label}</span>;
}

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div style={{ flex: '1 1 140px', padding: '16px 20px', background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb' }}>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: accent || '#111827' }}>{value}</div>
    </div>
  );
}

function Card({ title, color, count, children }: { title: string; color: string; count?: number; children: React.ReactNode }) {
  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden', marginBottom: 20 }}>
      <div style={{ padding: '14px 20px', borderBottom: '1px solid #f3f4f6', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 4, height: 20, borderRadius: 2, background: color }} />
        <h3 style={{ fontSize: 15, fontWeight: 700, color: '#111827', margin: 0 }}>{title}</h3>
        {count !== undefined && <span style={{ fontSize: 13, color: '#9ca3af', fontWeight: 500 }}>{count}건</span>}
      </div>
      <div style={{ padding: '12px 20px' }}>{children}</div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return <div style={{ textAlign: 'center', padding: '48px 20px', color: '#9ca3af', fontSize: 14 }}>{message}</div>;
}

/* ── 메인 ── */
export default function PrepackingPage() {
  const [tab, setTab] = useState<Tab>('instructions');
  const [vendors, setVendors] = useState<string[]>([]);
  const [vendor, setVendor] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [instructions, setInstructions] = useState<DailyInstructions | null>(null);
  const [predictions, setPredictions] = useState<PrepackingPrediction[]>([]);
  const [productionInputs, setProductionInputs] = useState<Record<string, { qty: number; location: string }>>({});
  const [locationSuggestions, setLocationSuggestions] = useState<string[]>([]);
  const [activeSuggestionKey, setActiveSuggestionKey] = useState<string | null>(null);
  const [activeProds, setActiveProds] = useState<PrepackingProduction[]>([]);
  const [useQtyInputs, setUseQtyInputs] = useState<Record<number, number>>({});
  const [analysisFrom, setAnalysisFrom] = useState(weeksAgo(8));
  const [analysisTo, setAnalysisTo] = useState(today());
  const [combos, setCombos] = useState<PrepackingCombo[]>([]);
  const [analysisInfo, setAnalysisInfo] = useState<any>(null);
  const [debugData, setDebugData] = useState<any>(null);
  const [accuracyHistory, setAccuracyHistory] = useState<AccuracyRecord[]>([]);
  const [efficiency, setEfficiency] = useState<EfficiencyStats | null>(null);
  const [allSettings, setAllSettings] = useState<PrepackingSettings[]>([]);
  const [editSettings, setEditSettings] = useState<PrepackingSettings>({
    vendor: '_default', min_predicted_qty: 1, min_frequency: 1, min_sku_count: 2, retention_days: 2,
  });

  useEffect(() => { getPrepackingVendors().then(setVendors).catch(() => {}); }, []);
  useEffect(() => { if (success) { const t = setTimeout(() => setSuccess(null), 3000); return () => clearTimeout(t); } }, [success]);

  const clear = () => { setError(null); setSuccess(null); };

  /* ── 데이터 로더 ── */
  const loadInstructions = useCallback(async () => {
    if (!vendor) return; setLoading(true); clear();
    try { setInstructions(await getDailyInstructions(vendor)); }
    catch (e) { setError(e instanceof Error ? e.message : '오류'); }
    finally { setLoading(false); }
  }, [vendor]);

  const loadPredictions = useCallback(async () => {
    if (!vendor) return; setLoading(true); clear();
    try {
      const res = await predictPrepacking({ vendor, target_date: tomorrow(), save: true });
      setPredictions(res.predictions);
      const inp: Record<string, { qty: number; location: string }> = {};
      res.predictions.forEach(p => { inp[p.combo_key] = { qty: p.predicted_qty, location: '' }; });
      setProductionInputs(inp);
    } catch (e) { setError(e instanceof Error ? e.message : '오류'); }
    finally { setLoading(false); }
  }, [vendor]);

  const loadInventory = useCallback(async () => {
    if (!vendor) return; setLoading(true); clear();
    try { setActiveProds(await getActiveProductions(vendor)); }
    catch (e) { setError(e instanceof Error ? e.message : '오류'); }
    finally { setLoading(false); }
  }, [vendor]);

  const loadAnalysis = useCallback(async () => {
    if (!vendor) return; setLoading(true); clear();
    try {
      const data = await analyzePrepackingCombos({ vendor, date_from: analysisFrom, date_to: analysisTo });
      setCombos(data.combos);
      setAnalysisInfo(data);
    } catch (e) { setError(e instanceof Error ? e.message : '오류'); }
    finally { setLoading(false); }
  }, [vendor, analysisFrom, analysisTo]);

  const loadAccuracy = useCallback(async () => {
    if (!vendor) return; setLoading(true); clear();
    try {
      const [h, e] = await Promise.all([getAccuracyHistory(vendor), getPrepackingEfficiency(vendor)]);
      setAccuracyHistory(h); setEfficiency(e);
    } catch (e) { setError(e instanceof Error ? e.message : '오류'); }
    finally { setLoading(false); }
  }, [vendor]);

  const loadSettings = useCallback(async () => {
    setLoading(true); clear();
    try {
      const data = await getAllPrepackingSettings();
      setAllSettings(data);
      const def = data.find(s => s.vendor === '_default');
      if (def) setEditSettings(def);
    } catch (e) { setError(e instanceof Error ? e.message : '오류'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!vendor && tab !== 'settings') return;
    const loaders: Record<Tab, () => void> = {
      instructions: loadInstructions, production: loadPredictions, inventory: loadInventory,
      analysis: loadAnalysis, accuracy: loadAccuracy, settings: loadSettings,
    };
    loaders[tab]?.();
  }, [tab, vendor]);

  /* ── 액션 ── */
  async function handleCreateProduction(key: string, detail: string, predQty: number) {
    const inp = productionInputs[key]; if (!inp || inp.qty <= 0) return; clear();
    try {
      await createPrepackingProduction({ vendor, target_date: tomorrow(), combo_key: key, combo_detail: detail, predicted_qty: predQty, produced_qty: inp.qty, location: inp.location });
      setSuccess(`${fmtCombo(key)} ${inp.qty}세트 등록`); loadPredictions();
    } catch (e) { setError(e instanceof Error ? e.message : '실패'); }
  }

  async function handleCreateAll() {
    clear(); let n = 0;
    for (const p of predictions) {
      const inp = productionInputs[p.combo_key]; if (!inp || inp.qty <= 0) continue;
      try { await createPrepackingProduction({ vendor, target_date: tomorrow(), combo_key: p.combo_key, combo_detail: p.combo_detail, predicted_qty: p.predicted_qty, produced_qty: inp.qty, location: inp.location }); n++; } catch {}
    }
    if (n) { setSuccess(`${n}건 등록 완료`); loadPredictions(); }
  }

  async function handleUse(id: number) {
    clear();
    try { await usePrepackingProduction(id, useQtyInputs[id] || 1); setSuccess('차감 완료'); loadInventory(); }
    catch (e) { setError(e instanceof Error ? e.message : '실패'); }
  }

  async function handleStatus(id: number, status: string) {
    clear();
    try { await updatePrepackingStatus(id, status); setSuccess('상태 변경'); loadInventory(); }
    catch (e) { setError(e instanceof Error ? e.message : '실패'); }
  }

  async function handleLocationInput(key: string, val: string) {
    setProductionInputs(prev => ({ ...prev, [key]: { ...prev[key], location: val } }));
    if (val.length >= 1 && vendor) {
      try { setLocationSuggestions(await suggestLocations(vendor, val)); setActiveSuggestionKey(key); }
      catch { setLocationSuggestions([]); }
    } else { setLocationSuggestions([]); setActiveSuggestionKey(null); }
  }

  async function handleSaveSettings() {
    clear();
    try { await savePrepackingSettings(editSettings); setSuccess('설정 저장 완료'); loadSettings(); }
    catch (e) { setError(e instanceof Error ? e.message : '실패'); }
  }

  async function handleUpdateAccuracy() {
    if (!vendor) return; clear();
    try { const r = await updatePrepackingAccuracy(vendor, today()); setSuccess(`정확도 업데이트: ${r.predictions_updated}건, MAPE ${r.avg_mape ?? 'N/A'}%`); loadAccuracy(); }
    catch (e) { setError(e instanceof Error ? e.message : '실패'); }
  }

  /* ── 탭 정의 ── */
  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'instructions', label: '오늘의 지시', icon: '📋' },
    { key: 'production',   label: '제작 등록',   icon: '🔨' },
    { key: 'inventory',    label: '재고 현황',   icon: '📦' },
    { key: 'analysis',     label: '조합 분석',   icon: '🔍' },
    { key: 'accuracy',     label: '정확도',      icon: '📊' },
    { key: 'settings',     label: '설정',        icon: '⚙️' },
  ];

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1280, margin: '0 auto' }}>
      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, color: '#111827', margin: 0 }}>프리패킹</h1>
        <select
          value={vendor} onChange={e => setVendor(e.target.value)}
          style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14, minWidth: 200, background: '#fff', color: vendor ? '#111827' : '#9ca3af' }}
        >
          <option value="">공급처 선택</option>
          {vendors.map(v => <option key={v} value={v}>{v}</option>)}
        </select>
      </div>

      {/* 탭 */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24, borderBottom: '1px solid #e5e7eb', overflowX: 'auto' }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            padding: '10px 16px', border: 'none', background: 'none', cursor: 'pointer',
            fontSize: 13, fontWeight: tab === t.key ? 700 : 500,
            color: tab === t.key ? '#2563eb' : '#6b7280',
            borderBottom: tab === t.key ? '2px solid #2563eb' : '2px solid transparent',
            whiteSpace: 'nowrap', transition: 'all 0.15s',
          }}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* 토스트 */}
      {error && <div style={{ padding: '12px 16px', marginBottom: 16, background: '#fef2f2', color: '#dc2626', borderRadius: 8, fontSize: 13, border: '1px solid #fecaca' }}>{error}</div>}
      {success && <div style={{ padding: '12px 16px', marginBottom: 16, background: '#f0fdf4', color: '#16a34a', borderRadius: 8, fontSize: 13, border: '1px solid #bbf7d0' }}>{success}</div>}
      {loading && <div style={{ textAlign: 'center', padding: 48, color: '#9ca3af' }}>불러오는 중...</div>}

      {/* ═══ 오늘의 지시 ═══ */}
      {tab === 'instructions' && !loading && instructions && (() => {
        const empty = !instructions.carry.length && !instructions.hold.length && !instructions.disassemble.length && !instructions.new_production.length;
        if (empty) return <EmptyState message="오늘의 지시 사항이 없습니다. 제작 등록 탭에서 시작하세요." />;
        return (
          <div>
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>{instructions.date} → <strong>{instructions.tomorrow}</strong></div>

            {instructions.new_production.length > 0 && (
              <Card title="신규 제작" color="#16a34a" count={instructions.new_production.length}>
                <table style={tbl}><thead><tr style={thr}>
                  <th style={th}>조합</th><th style={thC}>예측</th><th style={thC}>기존</th><th style={thC}>신규 필요</th>
                </tr></thead><tbody>
                  {instructions.new_production.map(n => (
                    <tr key={n.combo_key} style={trb}>
                      <td style={td}><ComboLabel combo_key={n.combo_key} /></td>
                      <td style={tdC}>{n.predicted_qty}</td>
                      <td style={tdC}>{n.existing_qty}</td>
                      <td style={{ ...tdC, fontWeight: 700, color: '#16a34a', fontSize: 16 }}>{n.new_qty}</td>
                    </tr>
                  ))}
                </tbody></table>
              </Card>
            )}

            {instructions.carry.length > 0 && (
              <Card title="유지 (내일도 필요)" color="#2563eb" count={instructions.carry.length}>
                <table style={tbl}><thead><tr style={thr}>
                  <th style={th}>조합</th><th style={thC}>잔여</th><th style={thC}>내일 예측</th><th style={th}>위치</th><th style={th}>제작일</th>
                </tr></thead><tbody>
                  {instructions.carry.map(c => (
                    <tr key={c.id} style={trb}>
                      <td style={td}><ComboLabel combo_key={c.combo_key} /></td>
                      <td style={tdC}>{c.remaining_qty}</td>
                      <td style={tdC}>{c.tomorrow_predicted}</td>
                      <td style={td}><LocBadge loc={c.location} /></td>
                      <td style={{ ...td, color: '#6b7280', fontSize: 12 }}>{c.target_date}</td>
                    </tr>
                  ))}
                </tbody></table>
              </Card>
            )}

            {instructions.hold.length > 0 && (
              <Card title="보류 (유지기간 내)" color="#ca8a04" count={instructions.hold.length}>
                <table style={tbl}><thead><tr style={thr}>
                  <th style={th}>조합</th><th style={thC}>잔여</th><th style={thC}>경과</th><th style={thC}>남은일</th><th style={th}>위치</th>
                </tr></thead><tbody>
                  {instructions.hold.map(h => (
                    <tr key={h.id} style={trb}>
                      <td style={td}><ComboLabel combo_key={h.combo_key} /></td>
                      <td style={tdC}>{h.remaining_qty}</td>
                      <td style={tdC}>{h.age_days}일</td>
                      <td style={tdC}>{h.expires_in}일</td>
                      <td style={td}><LocBadge loc={h.location} /></td>
                    </tr>
                  ))}
                </tbody></table>
              </Card>
            )}

            {instructions.disassemble.length > 0 && (
              <Card title="해체 지시" color="#dc2626" count={instructions.disassemble.length}>
                <table style={tbl}><thead><tr style={thr}>
                  <th style={th}>조합</th><th style={thC}>잔여</th><th style={thC}>경과</th><th style={th}>위치</th><th style={thC}>처리</th>
                </tr></thead><tbody>
                  {instructions.disassemble.map(d => (
                    <tr key={d.id} style={trb}>
                      <td style={td}><ComboLabel combo_key={d.combo_key} /></td>
                      <td style={tdC}>{d.remaining_qty}</td>
                      <td style={tdC}>{d.age_days}일</td>
                      <td style={td}><LocBadge loc={d.location} /></td>
                      <td style={tdC}>
                        <button onClick={() => handleStatus(d.id, 'disassembled')} style={btnDanger}>해체 완료</button>
                      </td>
                    </tr>
                  ))}
                </tbody></table>
              </Card>
            )}
          </div>
        );
      })()}

      {/* ═══ 제작 등록 ═══ */}
      {tab === 'production' && !loading && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: '#6b7280' }}>내일 <strong>{tomorrow()}</strong> 예측 기반</div>
            {predictions.length > 0 && <button onClick={handleCreateAll} style={btnPrimary}>전체 등록</button>}
          </div>

          {predictions.length === 0 ? (
            <EmptyState message={vendor ? '추천할 조합이 없습니다.' : '공급처를 선택하세요.'} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {predictions.map(pred => {
                const details = parseDetail(pred.combo_detail);
                const inp = productionInputs[pred.combo_key] || { qty: pred.predicted_qty, location: '' };
                return (
                  <div key={pred.combo_key} style={{ background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', padding: '16px 20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                      {/* 왼쪽: 조합 정보 */}
                      <div style={{ flex: '1 1 300px' }}>
                        <div style={{ fontWeight: 700, fontSize: 14, color: '#111827', marginBottom: 6 }}>{fmtCombo(pred.combo_key)}</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                          {details.map((d, i) => (
                            <span key={i} style={{ fontSize: 12, padding: '2px 8px', background: '#f3f4f6', borderRadius: 6, color: '#374151' }}>
                              {d.name} <strong>x{d.qty}</strong>
                              {d.barcode && <span style={{ color: '#9ca3af', marginLeft: 4 }}>{d.barcode}</span>}
                            </span>
                          ))}
                        </div>
                        <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
                          추천 수량: <strong style={{ color: '#2563eb' }}>{pred.predicted_qty}</strong> / 출현 {pred.frequency}회
                        </div>
                      </div>
                      {/* 오른쪽: 입력 */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                        <input type="number" min={0} value={inp.qty}
                          onChange={e => setProductionInputs(prev => ({ ...prev, [pred.combo_key]: { ...prev[pred.combo_key], qty: parseInt(e.target.value) || 0 } }))}
                          style={{ ...inputSm, width: 64, textAlign: 'center' }} />
                        <div style={{ position: 'relative' }}>
                          <input type="text" value={inp.location} placeholder="위치"
                            onChange={e => handleLocationInput(pred.combo_key, e.target.value)}
                            onBlur={() => setTimeout(() => setActiveSuggestionKey(null), 200)}
                            style={{ ...inputSm, width: 100 }} />
                          {activeSuggestionKey === pred.combo_key && locationSuggestions.length > 0 && (
                            <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.1)', maxHeight: 120, overflowY: 'auto' }}>
                              {locationSuggestions.map(loc => (
                                <div key={loc} onClick={() => { setProductionInputs(prev => ({ ...prev, [pred.combo_key]: { ...prev[pred.combo_key], location: loc } })); setActiveSuggestionKey(null); }}
                                  style={{ padding: '6px 10px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid #f3f4f6' }}
                                  onMouseEnter={e => (e.currentTarget.style.background = '#f9fafb')}
                                  onMouseLeave={e => (e.currentTarget.style.background = '#fff')}
                                >{loc}</div>
                              ))}
                            </div>
                          )}
                        </div>
                        <button onClick={() => handleCreateProduction(pred.combo_key, pred.combo_detail, pred.predicted_qty)} style={btnSuccess}>등록</button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ═══ 재고 현황 ═══ */}
      {tab === 'inventory' && !loading && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: '#6b7280' }}>활성 재고 <strong>{activeProds.length}</strong>건</div>
            <button onClick={loadInventory} style={btnOutline}>새로고침</button>
          </div>

          {activeProds.length === 0 ? <EmptyState message="활성 재고가 없습니다." /> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {activeProds.map(prod => {
                const st = STATUS_MAP[prod.status] || { label: prod.status, color: '#333', bg: '#f9fafb' };
                return (
                  <div key={prod.id} style={{ background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                    <div style={{ flex: '1 1 250px' }}>
                      <div style={{ fontWeight: 600, fontSize: 14, color: '#111827' }}>{fmtCombo(prod.combo_key)}</div>
                      <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>{prod.target_date} <LocBadge loc={prod.location} /></div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 11, color: '#9ca3af' }}>제작</div>
                        <div style={{ fontSize: 15, fontWeight: 600 }}>{prod.produced_qty}</div>
                      </div>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 11, color: '#9ca3af' }}>잔여</div>
                        <div style={{ fontSize: 15, fontWeight: 700, color: '#2563eb' }}>{prod.remaining_qty}</div>
                      </div>
                      <Badge label={st.label} color={st.color} bg={st.bg} />
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <input type="number" min={1} max={prod.remaining_qty}
                          value={useQtyInputs[prod.id] || 1}
                          onChange={e => setUseQtyInputs(prev => ({ ...prev, [prod.id]: parseInt(e.target.value) || 1 }))}
                          style={{ ...inputSm, width: 48, textAlign: 'center' }} />
                        <button onClick={() => handleUse(prod.id)} style={btnWarn}>차감</button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ═══ 조합 분석 ═══ */}
      {tab === 'analysis' && !loading && (
        <div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <input type="date" value={analysisFrom} onChange={e => setAnalysisFrom(e.target.value)} style={inputSm} />
            <span style={{ color: '#9ca3af' }}>~</span>
            <input type="date" value={analysisTo} onChange={e => setAnalysisTo(e.target.value)} style={inputSm} />
            <button onClick={loadAnalysis} style={btnPrimary}>분석</button>
          </div>

          {analysisInfo && (
            <>
              <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                <Stat label="전체 주문" value={analysisInfo.total_orders?.toLocaleString()} />
                <Stat label="합포장" value={analysisInfo.multi_item_orders?.toLocaleString()} accent="#2563eb" />
                <Stat label="단품" value={(analysisInfo.single_item_orders ?? 0).toLocaleString()} />
                <Stat label="조합 수" value={combos.length} accent="#7c3aed" />
                <Stat label="데이터" value={`${analysisInfo.data_weeks}주`} />
              </div>

              {/* 합포장 0건 진단 */}
              {analysisInfo.multi_item_orders === 0 && analysisInfo.total_orders > 0 && (
                <div style={{ padding: 16, marginBottom: 20, background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 12, fontSize: 13 }}>
                  <div style={{ fontWeight: 700, color: '#92400e', marginBottom: 8 }}>합포장이 감지되지 않습니다</div>
                  <div style={{ color: '#78350f', lineHeight: 1.8 }}>
                    <div>감지된 컬럼: <strong>{analysisInfo.detected_columns ? Object.entries(analysisInfo.detected_columns).map(([k, v]) => `${k}=${v}`).join(', ') : '없음'}</strong></div>
                    <div>어드민상품명수량: <strong>{analysisInfo.has_admin_col ? '있음' : '없음'}</strong> / 송장번호: <strong>{analysisInfo.has_invoice_col ? '있음' : '없음'}</strong> / 최소 SKU: <strong>{analysisInfo.min_sku_count ?? 2}</strong></div>
                    <div style={{ marginTop: 8, fontSize: 12, color: '#a16207' }}>
                      합포장 감지에는 <strong>어드민상품명수량</strong> 컬럼(한 행에 여러 SKU) 또는 <strong>같은 송장번호</strong>로 여러 행이 필요합니다.
                      배송통계 엑셀에 해당 컬럼이 포함되어 있는지 확인하세요.
                    </div>
                  </div>
                  <button onClick={async () => {
                    if (!vendor) return;
                    try { setDebugData(await debugPrepackingSampleRows(vendor, 10)); }
                    catch (e) { setError(e instanceof Error ? e.message : '오류'); }
                  }} style={{ ...btnOutline, marginTop: 12, fontSize: 12 }}>샘플 데이터 확인</button>
                </div>
              )}

              {/* 디버그 데이터 */}
              {debugData && (
                <div style={{ padding: 16, marginBottom: 20, background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 12, fontSize: 12, maxHeight: 400, overflow: 'auto' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: 13 }}>데이터 진단</span>
                    <button onClick={() => setDebugData(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 16 }}>x</button>
                  </div>
                  <div style={{ display: 'grid', gap: 4, color: '#374151' }}>
                    <div>총 행: <strong>{debugData.total_rows}</strong> / 배송건: <strong>{debugData.total_shipments}</strong> / 합포장: <strong>{debugData.multi_item_shipments}</strong></div>
                    <div>어드민상품명수량: <strong>{debugData.admin_col || '없음'}</strong> / 송장번호: <strong>{debugData.invoice_col || '없음'}</strong></div>
                    <div>전체 컬럼: <span style={{ color: '#6b7280' }}>{debugData.all_columns?.join(', ')}</span></div>
                  </div>
                  {debugData.first_rows?.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>샘플 행:</div>
                      {debugData.first_rows.map((r: any, i: number) => (
                        <div key={i} style={{ padding: 8, marginBottom: 4, background: '#fff', borderRadius: 6, border: '1px solid #e5e7eb' }}>
                          <div style={{ fontWeight: 600 }}>#{r.row_idx} (아이템 {r.item_count}개)</div>
                          {r.admin_product_qty_raw && <div style={{ color: '#6b7280', wordBreak: 'break-all' }}>원본: {r.admin_product_qty_raw}</div>}
                          <div style={{ color: '#2563eb' }}>추출: {JSON.stringify(r.extracted_items)}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {combos.length > 0 && (
            <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
              <table style={tbl}><thead><tr style={{ background: '#f9fafb' }}>
                <th style={{ ...th, width: 40, textAlign: 'center' }}>#</th>
                <th style={th}>조합</th>
                <th style={{ ...thC, width: 60 }}>횟수</th>
                {WEEKDAYS.map(d => <th key={d} style={{ ...thC, width: 40 }}>{d}</th>)}
              </tr></thead><tbody>
                {combos.slice(0, 50).map((c, i) => {
                  const details = parseDetail(c.combo_detail);
                  const maxDay = Math.max(...Object.values(c.day_counts).map(Number));
                  return (
                    <tr key={c.combo_key} style={trb}>
                      <td style={{ ...tdC, color: '#9ca3af', fontSize: 12 }}>{i + 1}</td>
                      <td style={td}>
                        {details.length > 0 ? (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                            {details.map((d, di) => (
                              <span key={di} style={{ fontSize: 12, padding: '1px 6px', background: '#f3f4f6', borderRadius: 4 }}>
                                {d.name} <strong>x{d.qty}</strong>
                              </span>
                            ))}
                          </div>
                        ) : <span style={{ fontSize: 13 }}>{fmtCombo(c.combo_key)}</span>}
                      </td>
                      <td style={{ ...tdC, fontWeight: 700 }}>{c.count}</td>
                      {WEEKDAYS.map((_, di) => {
                        const v = Number(c.day_counts[String(di)] || 0);
                        const intensity = maxDay > 0 ? v / maxDay : 0;
                        return (
                          <td key={di} style={{
                            ...tdC, fontSize: 12,
                            background: v > 0 ? `rgba(37, 99, 235, ${0.08 + intensity * 0.2})` : 'transparent',
                            fontWeight: v === maxDay && v > 0 ? 700 : 400,
                            color: v > 0 ? '#1e40af' : '#d1d5db',
                          }}>{v}</td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody></table>
            </div>
          )}
        </div>
      )}

      {/* ═══ 정확도 ═══ */}
      {tab === 'accuracy' && !loading && (
        <div>
          {efficiency && (
            <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
              <Stat label="총 제작" value={efficiency.total_produced} />
              <Stat label="총 사용" value={efficiency.total_used} />
              <Stat label="활용률" value={`${efficiency.utilization_rate}%`} accent="#16a34a" />
              <Stat label="폐기율" value={`${efficiency.waste_rate}%`} accent="#dc2626" />
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
            <button onClick={handleUpdateAccuracy} style={btnWarn}>오늘 정확도 업데이트</button>
          </div>

          {accuracyHistory.length === 0 ? <EmptyState message="정확도 데이터가 없습니다." /> : (
            <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
              <table style={tbl}><thead><tr style={{ background: '#f9fafb' }}>
                <th style={th}>날짜</th><th style={thC}>조합수</th><th style={thC}>MAPE</th><th style={thC}>예측</th><th style={thC}>실제</th><th style={thC}>차이</th>
              </tr></thead><tbody>
                {accuracyHistory.map(a => (
                  <tr key={a.target_date} style={trb}>
                    <td style={{ ...td, fontSize: 13 }}>{a.target_date}</td>
                    <td style={tdC}>{a.combo_count}</td>
                    <td style={{ ...tdC, fontWeight: 700, color: a.avg_mape !== null && a.avg_mape < 30 ? '#16a34a' : '#dc2626' }}>
                      {a.avg_mape !== null ? `${a.avg_mape}%` : '-'}
                    </td>
                    <td style={tdC}>{a.total_predicted}</td>
                    <td style={tdC}>{a.total_actual}</td>
                    <td style={{ ...tdC, color: a.total_actual !== null ? ((a.total_predicted - a.total_actual) > 0 ? '#dc2626' : '#16a34a') : '#9ca3af' }}>
                      {a.total_actual !== null ? (a.total_predicted - a.total_actual > 0 ? '+' : '') + (a.total_predicted - a.total_actual) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody></table>
            </div>
          )}
        </div>
      )}

      {/* ═══ 설정 ═══ */}
      {tab === 'settings' && !loading && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 360px', background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', padding: 24 }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 20, color: '#111827' }}>설정 편집</h3>
            <SettingField label="적용 대상">
              <select value={editSettings.vendor} onChange={e => {
                const v = e.target.value;
                const ex = allSettings.find(s => s.vendor === v);
                if (ex) setEditSettings(ex); else setEditSettings(prev => ({ ...prev, vendor: v }));
              }} style={inputFull}>
                <option value="_default">글로벌 기본값</option>
                {vendors.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </SettingField>
            <SettingField label="최소 예측 수량" hint="이 수량 이상 예측된 조합만 추천">
              <input type="number" min={1} value={editSettings.min_predicted_qty}
                onChange={e => setEditSettings(prev => ({ ...prev, min_predicted_qty: parseInt(e.target.value) || 1 }))} style={inputFull} />
            </SettingField>
            <SettingField label="최소 출현 빈도" hint="과거 데이터에서 이 횟수 이상 출현한 조합">
              <input type="number" min={1} value={editSettings.min_frequency}
                onChange={e => setEditSettings(prev => ({ ...prev, min_frequency: parseInt(e.target.value) || 1 }))} style={inputFull} />
            </SettingField>
            <SettingField label="최소 SKU 수" hint="2 = 2개 이상 SKU 조합만 합포장으로 인식">
              <input type="number" min={1} value={editSettings.min_sku_count}
                onChange={e => setEditSettings(prev => ({ ...prev, min_sku_count: parseInt(e.target.value) || 1 }))} style={inputFull} />
            </SettingField>
            <SettingField label="유지 기간 (일)" hint="초과 시 해체 지시">
              <input type="number" min={1} value={editSettings.retention_days}
                onChange={e => setEditSettings(prev => ({ ...prev, retention_days: parseInt(e.target.value) || 1 }))} style={inputFull} />
            </SettingField>
            <button onClick={handleSaveSettings} style={{ ...btnPrimary, width: '100%', padding: '10px 0', marginTop: 8 }}>저장</button>
          </div>

          {allSettings.length > 0 && (
            <div style={{ flex: '1 1 300px', background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden', alignSelf: 'flex-start' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid #f3f4f6', fontWeight: 700, fontSize: 15, color: '#111827' }}>현재 설정</div>
              <table style={tbl}><thead><tr style={{ background: '#f9fafb' }}>
                <th style={th}>대상</th><th style={thC}>예측</th><th style={thC}>빈도</th><th style={thC}>SKU</th><th style={thC}>유지</th>
              </tr></thead><tbody>
                {allSettings.map(s => (
                  <tr key={s.vendor} style={trb}>
                    <td style={{ ...td, fontWeight: 600 }}>{s.vendor === '_default' ? '기본값' : s.vendor}</td>
                    <td style={tdC}>{s.min_predicted_qty}</td>
                    <td style={tdC}>{s.min_frequency}</td>
                    <td style={tdC}>{s.min_sku_count}</td>
                    <td style={tdC}>{s.retention_days}일</td>
                  </tr>
                ))}
              </tbody></table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── 작은 컴포넌트 ── */
function ComboLabel({ combo_key }: { combo_key: string }) {
  const parts = combo_key.split('|');
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {parts.map((p, i) => {
        const [name, qty] = p.split(':');
        return (
          <span key={i} style={{ fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 2 }}>
            {i > 0 && <span style={{ color: '#d1d5db', margin: '0 2px' }}>+</span>}
            <span style={{ fontWeight: 600, color: '#111827' }}>{name}</span>
            <span style={{ color: '#2563eb', fontWeight: 700 }}>x{qty}</span>
          </span>
        );
      })}
    </div>
  );
}

function LocBadge({ loc }: { loc: string }) {
  if (!loc) return null;
  return <span style={{ fontSize: 11, padding: '1px 6px', background: '#f3f4f6', borderRadius: 4, color: '#6b7280', marginLeft: 4 }}>{loc}</span>;
}

function SettingField({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>{label}</label>
      {children}
      {hint && <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{hint}</div>}
    </div>
  );
}

/* ── 스타일 상수 ── */
const tbl: React.CSSProperties = { width: '100%', borderCollapse: 'collapse' };
const thr: React.CSSProperties = { background: '#f9fafb' };
const trb: React.CSSProperties = { borderBottom: '1px solid #f3f4f6' };
const th: React.CSSProperties = { padding: '10px 12px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: '#6b7280', whiteSpace: 'nowrap' };
const thC: React.CSSProperties = { ...th, textAlign: 'center' };
const td: React.CSSProperties = { padding: '10px 12px', fontSize: 13, verticalAlign: 'middle' };
const tdC: React.CSSProperties = { ...td, textAlign: 'center' };

const inputSm: React.CSSProperties = { padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, background: '#fff' };
const inputFull: React.CSSProperties = { ...inputSm, width: '100%' };

const btnBase: React.CSSProperties = { padding: '6px 14px', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' };
const btnPrimary: React.CSSProperties = { ...btnBase, background: '#2563eb', color: '#fff' };
const btnSuccess: React.CSSProperties = { ...btnBase, background: '#16a34a', color: '#fff' };
const btnWarn: React.CSSProperties = { ...btnBase, background: '#f59e0b', color: '#fff' };
const btnDanger: React.CSSProperties = { ...btnBase, background: '#dc2626', color: '#fff' };
const btnOutline: React.CSSProperties = { ...btnBase, background: '#fff', color: '#374151', border: '1px solid #d1d5db' };

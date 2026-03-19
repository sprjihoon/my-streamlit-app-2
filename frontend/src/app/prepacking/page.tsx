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
  type PrepackingCombo,
  type PrepackingPrediction,
  type PrepackingProduction,
  type DailyInstructions,
  type PrepackingSettings,
  type AccuracyRecord,
  type EfficiencyStats,
  type ComboDetail,
} from '@/lib/api';

const WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일'];
const STATUS_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: '사용가능', color: '#2e7d32', bg: '#e8f5e9' },
  carried: { label: '이월(유지)', color: '#1565c0', bg: '#e3f2fd' },
  held: { label: '보류중', color: '#f57f17', bg: '#fff8e1' },
  disassemble: { label: '해체지시', color: '#c62828', bg: '#ffebee' },
  disassembled: { label: '해체완료', color: '#757575', bg: '#f5f5f5' },
  depleted: { label: '소진', color: '#9e9e9e', bg: '#fafafa' },
};

function parseComboDetail(detailStr: string): ComboDetail[] {
  try {
    return JSON.parse(detailStr);
  } catch {
    return [];
  }
}

function formatComboKey(key: string): string {
  return key.split('|').map(part => {
    const [name, qty] = part.split(':');
    return `${name} x${qty}`;
  }).join(' + ');
}

function todayStr(): string {
  return new Date().toISOString().split('T')[0];
}

function tomorrowStr(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().split('T')[0];
}

function weeksAgoStr(weeks: number): string {
  const d = new Date();
  d.setDate(d.getDate() - weeks * 7);
  return d.toISOString().split('T')[0];
}

export default function PrepackingPage() {
  const [tab, setTab] = useState<'instructions' | 'production' | 'inventory' | 'analysis' | 'accuracy' | 'settings'>('instructions');
  const [vendors, setVendors] = useState<string[]>([]);
  const [vendor, setVendor] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 오늘의 지시
  const [instructions, setInstructions] = useState<DailyInstructions | null>(null);

  // 제작 기록
  const [predictions, setPredictions] = useState<PrepackingPrediction[]>([]);
  const [productionInputs, setProductionInputs] = useState<Record<string, { qty: number; location: string }>>({});
  const [locationSuggestions, setLocationSuggestions] = useState<string[]>([]);
  const [activeSuggestionKey, setActiveSuggestionKey] = useState<string | null>(null);

  // 재고 현황
  const [activeProds, setActiveProds] = useState<PrepackingProduction[]>([]);
  const [useQtyInputs, setUseQtyInputs] = useState<Record<number, number>>({});

  // 조합 분석
  const [analysisDateFrom, setAnalysisDateFrom] = useState(weeksAgoStr(8));
  const [analysisDateTo, setAnalysisDateTo] = useState(todayStr());
  const [combos, setCombos] = useState<PrepackingCombo[]>([]);
  const [analysisInfo, setAnalysisInfo] = useState<{
    total_orders: number; multi_item_orders: number; data_weeks: number;
    single_item_orders?: number; parse_failures?: number;
    min_sku_count?: number; has_admin_col?: boolean; has_barcode_col?: boolean;
    detected_columns?: Record<string, string>;
  } | null>(null);

  // 정확도
  const [accuracyHistory, setAccuracyHistory] = useState<AccuracyRecord[]>([]);
  const [efficiency, setEfficiency] = useState<EfficiencyStats | null>(null);

  // 설정
  const [allSettings, setAllSettings] = useState<PrepackingSettings[]>([]);
  const [editSettings, setEditSettings] = useState<PrepackingSettings>({
    vendor: '_default', min_predicted_qty: 1, min_frequency: 1, min_sku_count: 2, retention_days: 2,
  });

  useEffect(() => {
    getPrepackingVendors().then(setVendors).catch(() => {});
  }, []);

  const clearMessages = () => { setError(null); setSuccess(null); };

  // ── 오늘의 지시 로드 ──
  const loadInstructions = useCallback(async () => {
    if (!vendor) return;
    setLoading(true); clearMessages();
    try {
      const data = await getDailyInstructions(vendor);
      setInstructions(data);
    } catch (e) { setError(e instanceof Error ? e.message : '오류 발생'); }
    finally { setLoading(false); }
  }, [vendor]);

  // ── 예측 로드 (제작 탭) ──
  const loadPredictions = useCallback(async () => {
    if (!vendor) return;
    setLoading(true); clearMessages();
    try {
      const res = await predictPrepacking({ vendor, target_date: tomorrowStr(), save: true });
      setPredictions(res.predictions);
      const inputs: Record<string, { qty: number; location: string }> = {};
      res.predictions.forEach(p => { inputs[p.combo_key] = { qty: p.predicted_qty, location: '' }; });
      setProductionInputs(inputs);
    } catch (e) { setError(e instanceof Error ? e.message : '오류 발생'); }
    finally { setLoading(false); }
  }, [vendor]);

  // ── 재고 로드 ──
  const loadInventory = useCallback(async () => {
    if (!vendor) return;
    setLoading(true); clearMessages();
    try {
      const data = await getActiveProductions(vendor);
      setActiveProds(data);
    } catch (e) { setError(e instanceof Error ? e.message : '오류 발생'); }
    finally { setLoading(false); }
  }, [vendor]);

  // ── 조합 분석 ──
  const loadAnalysis = useCallback(async () => {
    if (!vendor) return;
    setLoading(true); clearMessages();
    try {
      const data = await analyzePrepackingCombos({ vendor, date_from: analysisDateFrom, date_to: analysisDateTo });
      setCombos(data.combos);
      setAnalysisInfo({
        total_orders: data.total_orders, multi_item_orders: data.multi_item_orders, data_weeks: data.data_weeks,
        single_item_orders: data.single_item_orders, parse_failures: data.parse_failures,
        min_sku_count: data.min_sku_count, has_admin_col: data.has_admin_col, has_barcode_col: data.has_barcode_col,
        detected_columns: data.detected_columns,
      });
    } catch (e) { setError(e instanceof Error ? e.message : '오류 발생'); }
    finally { setLoading(false); }
  }, [vendor, analysisDateFrom, analysisDateTo]);

  // ── 정확도 로드 ──
  const loadAccuracy = useCallback(async () => {
    if (!vendor) return;
    setLoading(true); clearMessages();
    try {
      const [hist, eff] = await Promise.all([
        getAccuracyHistory(vendor),
        getPrepackingEfficiency(vendor),
      ]);
      setAccuracyHistory(hist);
      setEfficiency(eff);
    } catch (e) { setError(e instanceof Error ? e.message : '오류 발생'); }
    finally { setLoading(false); }
  }, [vendor]);

  // ── 설정 로드 ──
  const loadSettings = useCallback(async () => {
    setLoading(true); clearMessages();
    try {
      const data = await getAllPrepackingSettings();
      setAllSettings(data);
      const def = data.find(s => s.vendor === '_default');
      if (def) setEditSettings(def);
    } catch (e) { setError(e instanceof Error ? e.message : '오류 발생'); }
    finally { setLoading(false); }
  }, []);

  // 탭 변경 시 데이터 로드
  useEffect(() => {
    if (!vendor && tab !== 'settings') return;
    if (tab === 'instructions') loadInstructions();
    else if (tab === 'production') loadPredictions();
    else if (tab === 'inventory') loadInventory();
    else if (tab === 'analysis') loadAnalysis();
    else if (tab === 'accuracy') loadAccuracy();
    else if (tab === 'settings') loadSettings();
  }, [tab, vendor]);

  // ── 제작 등록 ──
  async function handleCreateProduction(comboKey: string, comboDetail: string, predictedQty: number) {
    const input = productionInputs[comboKey];
    if (!input || input.qty <= 0) return;
    clearMessages();
    try {
      await createPrepackingProduction({
        vendor, target_date: tomorrowStr(), combo_key: comboKey,
        combo_detail: comboDetail, predicted_qty: predictedQty,
        produced_qty: input.qty, location: input.location,
      });
      setSuccess(`${formatComboKey(comboKey)} ${input.qty}세트 제작 등록 완료`);
      loadPredictions();
    } catch (e) { setError(e instanceof Error ? e.message : '등록 실패'); }
  }

  // ── 전체 제작 일괄 등록 ──
  async function handleCreateAllProductions() {
    clearMessages();
    let created = 0;
    for (const pred of predictions) {
      const input = productionInputs[pred.combo_key];
      if (!input || input.qty <= 0) continue;
      try {
        await createPrepackingProduction({
          vendor, target_date: tomorrowStr(), combo_key: pred.combo_key,
          combo_detail: pred.combo_detail, predicted_qty: pred.predicted_qty,
          produced_qty: input.qty, location: input.location,
        });
        created++;
      } catch { /* skip */ }
    }
    if (created > 0) {
      setSuccess(`${created}건 제작 등록 완료`);
      loadPredictions();
    }
  }

  // ── 사용 차감 ──
  async function handleUse(prodId: number) {
    const qty = useQtyInputs[prodId] || 1;
    clearMessages();
    try {
      await usePrepackingProduction(prodId, qty);
      setSuccess('차감 완료');
      loadInventory();
    } catch (e) { setError(e instanceof Error ? e.message : '차감 실패'); }
  }

  // ── 상태 변경 ──
  async function handleStatusChange(prodId: number, newStatus: string) {
    clearMessages();
    try {
      await updatePrepackingStatus(prodId, newStatus);
      setSuccess('상태 변경 완료');
      loadInventory();
    } catch (e) { setError(e instanceof Error ? e.message : '상태 변경 실패'); }
  }

  // ── 로케이션 자동완성 ──
  async function handleLocationInput(comboKey: string, value: string) {
    setProductionInputs(prev => ({ ...prev, [comboKey]: { ...prev[comboKey], location: value } }));
    if (value.length >= 1 && vendor) {
      try {
        const suggestions = await suggestLocations(vendor, value);
        setLocationSuggestions(suggestions);
        setActiveSuggestionKey(comboKey);
      } catch { setLocationSuggestions([]); }
    } else {
      setLocationSuggestions([]);
      setActiveSuggestionKey(null);
    }
  }

  // ── 설정 저장 ──
  async function handleSaveSettings() {
    clearMessages();
    try {
      await savePrepackingSettings(editSettings);
      setSuccess('설정 저장 완료');
      loadSettings();
    } catch (e) { setError(e instanceof Error ? e.message : '설정 저장 실패'); }
  }

  // ── 정확도 업데이트 ──
  async function handleUpdateAccuracy() {
    if (!vendor) return;
    clearMessages();
    try {
      const result = await updatePrepackingAccuracy(vendor, todayStr());
      setSuccess(`정확도 업데이트: ${result.predictions_updated}건, 평균 MAPE: ${result.avg_mape ?? 'N/A'}%`);
      loadAccuracy();
    } catch (e) { setError(e instanceof Error ? e.message : '업데이트 실패'); }
  }

  const tabStyle = (t: string) => ({
    padding: '0.5rem 1rem',
    border: 'none',
    borderBottom: tab === t ? '3px solid #1976d2' : '3px solid transparent',
    background: 'none',
    cursor: 'pointer',
    fontWeight: tab === t ? 700 : 400,
    color: tab === t ? '#1976d2' : '#666',
    fontSize: '0.9rem',
  });

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1200 }}>
      <h1 style={{ marginBottom: '0.5rem' }}>📦 프리패킹 관리</h1>

      {/* 공급처 선택 */}
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '1rem' }}>
        <label style={{ fontWeight: 600 }}>공급처:</label>
        <select
          value={vendor}
          onChange={e => setVendor(e.target.value)}
          style={{ padding: '0.4rem 0.75rem', borderRadius: 4, border: '1px solid #ccc', minWidth: 200 }}
        >
          <option value="">선택하세요</option>
          {vendors.map(v => <option key={v} value={v}>{v}</option>)}
        </select>
      </div>

      {/* 탭 */}
      <div style={{ borderBottom: '1px solid #ddd', marginBottom: '1rem', display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
        <button style={tabStyle('instructions')} onClick={() => setTab('instructions')}>오늘의 지시</button>
        <button style={tabStyle('production')} onClick={() => setTab('production')}>제작 등록</button>
        <button style={tabStyle('inventory')} onClick={() => setTab('inventory')}>재고 현황</button>
        <button style={tabStyle('analysis')} onClick={() => setTab('analysis')}>조합 분석</button>
        <button style={tabStyle('accuracy')} onClick={() => setTab('accuracy')}>정확도/효율</button>
        <button style={tabStyle('settings')} onClick={() => setTab('settings')}>설정</button>
      </div>

      {/* 메시지 */}
      {error && <div style={{ padding: '0.75rem', marginBottom: '1rem', backgroundColor: '#ffebee', color: '#c62828', borderRadius: 4 }}>{error}</div>}
      {success && <div style={{ padding: '0.75rem', marginBottom: '1rem', backgroundColor: '#e8f5e9', color: '#2e7d32', borderRadius: 4 }}>{success}</div>}
      {loading && <div style={{ padding: '1rem', textAlign: 'center', color: '#666' }}>로딩 중...</div>}

      {/* ═══ 오늘의 지시 ═══ */}
      {tab === 'instructions' && !loading && instructions && (
        <div>
          <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>
            {instructions.date} → {instructions.tomorrow} 지시
          </h2>

          {/* 유지 */}
          {instructions.carry.length > 0 && (
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ color: '#1565c0', marginBottom: '0.5rem' }}>✅ 유지 (내일도 필요)</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#e3f2fd' }}>
                    <th style={thStyle}>조합</th><th style={thStyle}>잔여</th><th style={thStyle}>내일 예측</th><th style={thStyle}>위치</th><th style={thStyle}>제작일</th>
                  </tr>
                </thead>
                <tbody>
                  {instructions.carry.map(c => (
                    <tr key={c.id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={tdStyle}>{formatComboKey(c.combo_key)}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{c.remaining_qty}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{c.tomorrow_predicted}</td>
                      <td style={tdStyle}>{c.location}</td>
                      <td style={tdStyle}>{c.target_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* 보류 */}
          {instructions.hold.length > 0 && (
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ color: '#f57f17', marginBottom: '0.5rem' }}>⏳ 보류 (유지기간 내)</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#fff8e1' }}>
                    <th style={thStyle}>조합</th><th style={thStyle}>잔여</th><th style={thStyle}>경과일</th><th style={thStyle}>남은일</th><th style={thStyle}>위치</th>
                  </tr>
                </thead>
                <tbody>
                  {instructions.hold.map(h => (
                    <tr key={h.id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={tdStyle}>{formatComboKey(h.combo_key)}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{h.remaining_qty}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{h.age_days}일</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{h.expires_in}일</td>
                      <td style={tdStyle}>{h.location}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* 해체 지시 */}
          {instructions.disassemble.length > 0 && (
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ color: '#c62828', marginBottom: '0.5rem' }}>🔴 해체 지시 (유지기간 초과)</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#ffebee' }}>
                    <th style={thStyle}>조합</th><th style={thStyle}>잔여</th><th style={thStyle}>경과일</th><th style={thStyle}>위치</th><th style={thStyle}>처리</th>
                  </tr>
                </thead>
                <tbody>
                  {instructions.disassemble.map(d => (
                    <tr key={d.id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={tdStyle}>{formatComboKey(d.combo_key)}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{d.remaining_qty}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{d.age_days}일</td>
                      <td style={tdStyle}>{d.location}</td>
                      <td style={tdStyle}>
                        <button
                          onClick={() => handleStatusChange(d.id, 'disassembled')}
                          style={{ padding: '0.25rem 0.5rem', backgroundColor: '#c62828', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.8rem' }}
                        >해체 완료</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* 신규 제작 추천 */}
          {instructions.new_production.length > 0 && (
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ color: '#2e7d32', marginBottom: '0.5rem' }}>🆕 신규 제작 추천</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#e8f5e9' }}>
                    <th style={thStyle}>조합</th><th style={thStyle}>예측</th><th style={thStyle}>기존유지</th><th style={thStyle}>신규필요</th>
                  </tr>
                </thead>
                <tbody>
                  {instructions.new_production.map(n => (
                    <tr key={n.combo_key} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={tdStyle}>{formatComboKey(n.combo_key)}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{n.predicted_qty}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{n.existing_qty}</td>
                      <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, color: '#2e7d32' }}>{n.new_qty}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!instructions.carry.length && !instructions.hold.length && !instructions.disassemble.length && !instructions.new_production.length && (
            <div style={{ textAlign: 'center', padding: '2rem', color: '#666' }}>
              <p style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 600 }}>오늘의 지시 사항이 없습니다.</p>
              <p style={{ fontSize: '0.9rem', color: '#999', lineHeight: 1.6 }}>
                아직 제작된 프리패킹이 없거나, 내일 예측 데이터가 부족합니다.<br />
                먼저 <strong>&quot;제작 등록&quot;</strong> 탭에서 예측 추천을 확인하고 제작을 시작하세요.<br />
                배송통계 데이터가 많을수록 예측이 정확해집니다.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ═══ 제작 등록 ═══ */}
      {tab === 'production' && !loading && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1.1rem' }}>내일({tomorrowStr()}) 프리패킹 제작</h2>
            {predictions.length > 0 && (
              <button
                onClick={handleCreateAllProductions}
                style={{ padding: '0.5rem 1rem', backgroundColor: '#1976d2', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
              >전체 등록</button>
            )}
          </div>

          {predictions.length === 0 ? (
            <p style={{ color: '#999', textAlign: 'center', padding: '2rem' }}>
              {vendor ? '추천할 조합이 없습니다. (데이터 부족 또는 설정 기준 미달)' : '공급처를 선택하세요.'}
            </p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={thStyle}>조합</th>
                  <th style={thStyle}>상세</th>
                  <th style={thStyle}>추천</th>
                  <th style={thStyle}>제작 수량</th>
                  <th style={thStyle}>보관 위치</th>
                  <th style={thStyle}>등록</th>
                </tr>
              </thead>
              <tbody>
                {predictions.map(pred => {
                  const details = parseComboDetail(pred.combo_detail);
                  const input = productionInputs[pred.combo_key] || { qty: pred.predicted_qty, location: '' };
                  return (
                    <tr key={pred.combo_key} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={tdStyle}>{formatComboKey(pred.combo_key)}</td>
                      <td style={{ ...tdStyle, fontSize: '0.8rem' }}>
                        {details.map((d, i) => (
                          <div key={i}>
                            {d.name} x{d.qty}
                            {d.barcode && <span style={{ color: '#999', marginLeft: 4 }}>({d.barcode})</span>}
                          </div>
                        ))}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{pred.predicted_qty}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>
                        <input
                          type="number" min={0} value={input.qty}
                          onChange={e => setProductionInputs(prev => ({
                            ...prev, [pred.combo_key]: { ...prev[pred.combo_key], qty: parseInt(e.target.value) || 0 }
                          }))}
                          style={{ width: 60, padding: '0.25rem', textAlign: 'center', border: '1px solid #ccc', borderRadius: 4 }}
                        />
                      </td>
                      <td style={{ ...tdStyle, position: 'relative' }}>
                        <input
                          type="text" value={input.location}
                          onChange={e => handleLocationInput(pred.combo_key, e.target.value)}
                          onBlur={() => setTimeout(() => setActiveSuggestionKey(null), 200)}
                          placeholder="예: A-3-2"
                          style={{ width: '100%', padding: '0.25rem', border: '1px solid #ccc', borderRadius: 4 }}
                        />
                        {activeSuggestionKey === pred.combo_key && locationSuggestions.length > 0 && (
                          <div style={{
                            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
                            backgroundColor: '#fff', border: '1px solid #ccc', borderRadius: 4, maxHeight: 150, overflowY: 'auto',
                          }}>
                            {locationSuggestions.map(loc => (
                              <div
                                key={loc}
                                onClick={() => {
                                  setProductionInputs(prev => ({ ...prev, [pred.combo_key]: { ...prev[pred.combo_key], location: loc } }));
                                  setActiveSuggestionKey(null);
                                }}
                                style={{ padding: '0.25rem 0.5rem', cursor: 'pointer', fontSize: '0.85rem' }}
                                onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#e3f2fd')}
                                onMouseLeave={e => (e.currentTarget.style.backgroundColor = '#fff')}
                              >{loc}</div>
                            ))}
                          </div>
                        )}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>
                        <button
                          onClick={() => handleCreateProduction(pred.combo_key, pred.combo_detail, pred.predicted_qty)}
                          style={{ padding: '0.25rem 0.75rem', backgroundColor: '#4CAF50', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.85rem' }}
                        >등록</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ═══ 재고 현황 ═══ */}
      {tab === 'inventory' && !loading && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1.1rem' }}>프리패킹 재고 현황</h2>
            <button onClick={loadInventory} style={{ padding: '0.4rem 0.75rem', backgroundColor: '#1976d2', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.85rem' }}>새로고침</button>
          </div>

          {activeProds.length === 0 ? (
            <p style={{ color: '#999', textAlign: 'center', padding: '2rem' }}>활성 재고가 없습니다.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={thStyle}>조합</th><th style={thStyle}>제작</th><th style={thStyle}>잔여</th>
                  <th style={thStyle}>위치</th><th style={thStyle}>상태</th><th style={thStyle}>제작일</th><th style={thStyle}>사용</th>
                </tr>
              </thead>
              <tbody>
                {activeProds.map(prod => {
                  const st = STATUS_LABELS[prod.status] || { label: prod.status, color: '#333', bg: '#fff' };
                  return (
                    <tr key={prod.id} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={tdStyle}>{formatComboKey(prod.combo_key)}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{prod.produced_qty}</td>
                      <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700 }}>{prod.remaining_qty}</td>
                      <td style={tdStyle}>{prod.location}</td>
                      <td style={tdStyle}>
                        <span style={{ padding: '0.15rem 0.5rem', borderRadius: 12, fontSize: '0.75rem', backgroundColor: st.bg, color: st.color, fontWeight: 600 }}>
                          {st.label}
                        </span>
                      </td>
                      <td style={tdStyle}>{prod.target_date}</td>
                      <td style={{ ...tdStyle, display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                        <input
                          type="number" min={1} max={prod.remaining_qty}
                          value={useQtyInputs[prod.id] || 1}
                          onChange={e => setUseQtyInputs(prev => ({ ...prev, [prod.id]: parseInt(e.target.value) || 1 }))}
                          style={{ width: 50, padding: '0.2rem', textAlign: 'center', border: '1px solid #ccc', borderRadius: 4 }}
                        />
                        <button
                          onClick={() => handleUse(prod.id)}
                          style={{ padding: '0.2rem 0.5rem', backgroundColor: '#ff9800', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: '0.8rem' }}
                        >차감</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ═══ 조합 분석 ═══ */}
      {tab === 'analysis' && !loading && (
        <div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <input type="date" value={analysisDateFrom} onChange={e => setAnalysisDateFrom(e.target.value)} style={inputStyle} />
            <span>~</span>
            <input type="date" value={analysisDateTo} onChange={e => setAnalysisDateTo(e.target.value)} style={inputStyle} />
            <button onClick={loadAnalysis} style={{ padding: '0.4rem 0.75rem', backgroundColor: '#1976d2', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>분석</button>
          </div>

          {analysisInfo && (
            <div>
              <div style={{ display: 'flex', gap: '1rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
                <div style={statCard}>전체 주문: <strong>{analysisInfo.total_orders.toLocaleString()}</strong></div>
                <div style={statCard}>합포장 주문: <strong>{analysisInfo.multi_item_orders.toLocaleString()}</strong></div>
                <div style={statCard}>단품 주문: <strong>{(analysisInfo.single_item_orders ?? 0).toLocaleString()}</strong></div>
                <div style={statCard}>데이터 기간: <strong>{analysisInfo.data_weeks}주</strong></div>
                <div style={statCard}>조합 수: <strong>{combos.length}</strong></div>
              </div>
              {analysisInfo.multi_item_orders === 0 && analysisInfo.total_orders > 0 && (
                <div style={{ padding: '0.75rem', backgroundColor: '#fff3e0', borderRadius: 6, marginBottom: '1rem', fontSize: '0.85rem', color: '#e65100' }}>
                  <strong>합포장 주문이 0건입니다.</strong><br/>
                  전체 {analysisInfo.total_orders}건 중 단품 {analysisInfo.single_item_orders ?? 0}건, 파싱실패 {analysisInfo.parse_failures ?? 0}건<br/>
                  감지된 컬럼: {analysisInfo.detected_columns ? Object.entries(analysisInfo.detected_columns).map(([k,v]) => `${k}=${v}`).join(', ') : 'N/A'}<br/>
                  어드민상품명수량 컬럼: {analysisInfo.has_admin_col ? '있음' : '없음'} / 최소 SKU 수: {analysisInfo.min_sku_count ?? 2}
                </div>
              )}
            </div>
          )}

          {combos.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={thStyle}>#</th><th style={thStyle}>조합 상세</th><th style={thStyle}>횟수</th>
                  {WEEKDAYS.map(d => <th key={d} style={{ ...thStyle, textAlign: 'center', width: 40 }}>{d}</th>)}
                </tr>
              </thead>
              <tbody>
                {combos.slice(0, 50).map((c, i) => {
                  const details = parseComboDetail(c.combo_detail);
                  return (
                    <tr key={c.combo_key} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ ...tdStyle, textAlign: 'center', color: '#999', verticalAlign: 'top' }}>{i + 1}</td>
                      <td style={{ ...tdStyle, minWidth: 250 }}>
                        {details.length > 0 ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                            {details.map((d, di) => (
                              <div key={di} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
                                <span style={{ fontWeight: 600 }}>{d.name}</span>
                                <span style={{ color: '#1976d2', fontWeight: 700 }}>x{d.qty}</span>
                                {d.barcode && (
                                  <span style={{ fontSize: '0.75rem', color: '#888', backgroundColor: '#f5f5f5', padding: '0.1rem 0.3rem', borderRadius: 3 }}>
                                    {d.barcode}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <span style={{ fontSize: '0.85rem' }}>{formatComboKey(c.combo_key)}</span>
                        )}
                      </td>
                      <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, verticalAlign: 'top' }}>{c.count}</td>
                      {WEEKDAYS.map((_, di) => (
                        <td key={di} style={{ ...tdStyle, textAlign: 'center', fontSize: '0.85rem', verticalAlign: 'top' }}>
                          {c.day_counts[String(di)] || 0}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ═══ 정확도/효율 ═══ */}
      {tab === 'accuracy' && !loading && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1.1rem' }}>정확도 & 효율</h2>
            <button onClick={handleUpdateAccuracy} style={{ padding: '0.4rem 0.75rem', backgroundColor: '#ff9800', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>오늘 정확도 업데이트</button>
          </div>

          {efficiency && (
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
              <div style={statCard}>총 제작: <strong>{efficiency.total_produced}</strong></div>
              <div style={statCard}>총 사용: <strong>{efficiency.total_used}</strong></div>
              <div style={{ ...statCard, borderColor: '#4CAF50' }}>활용률: <strong>{efficiency.utilization_rate}%</strong></div>
              <div style={{ ...statCard, borderColor: '#f44336' }}>폐기율: <strong>{efficiency.waste_rate}%</strong></div>
              <div style={statCard}>소진: <strong>{efficiency.depleted_count}</strong></div>
              <div style={statCard}>해체: <strong>{efficiency.disassembled_count}</strong></div>
            </div>
          )}

          {accuracyHistory.length > 0 ? (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={thStyle}>날짜</th><th style={thStyle}>조합수</th><th style={thStyle}>평균 MAPE</th>
                  <th style={thStyle}>예측합</th><th style={thStyle}>실제합</th><th style={thStyle}>차이</th>
                </tr>
              </thead>
              <tbody>
                {accuracyHistory.map(a => (
                  <tr key={a.target_date} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={tdStyle}>{a.target_date}</td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>{a.combo_count}</td>
                    <td style={{ ...tdStyle, textAlign: 'center', fontWeight: 700, color: a.avg_mape !== null && a.avg_mape < 30 ? '#2e7d32' : '#c62828' }}>
                      {a.avg_mape !== null ? `${a.avg_mape}%` : '-'}
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>{a.total_predicted}</td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>{a.total_actual}</td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {a.total_actual !== null ? (a.total_predicted - a.total_actual) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p style={{ color: '#999', textAlign: 'center', padding: '2rem' }}>정확도 데이터가 없습니다.</p>
          )}
        </div>
      )}

      {/* ═══ 설정 ═══ */}
      {tab === 'settings' && !loading && (
        <div>
          <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>프리패킹 설정</h2>

          <div style={{ backgroundColor: '#f9f9f9', padding: '1.5rem', borderRadius: 8, marginBottom: '1.5rem', maxWidth: 500 }}>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 600 }}>적용 대상</label>
              <select
                value={editSettings.vendor}
                onChange={e => {
                  const v = e.target.value;
                  const existing = allSettings.find(s => s.vendor === v);
                  if (existing) setEditSettings(existing);
                  else setEditSettings(prev => ({ ...prev, vendor: v }));
                }}
                style={{ width: '100%', padding: '0.4rem', border: '1px solid #ccc', borderRadius: 4 }}
              >
                <option value="_default">글로벌 기본값</option>
                {vendors.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 600 }}>최소 예측 수량</label>
              <input
                type="number" min={1} value={editSettings.min_predicted_qty}
                onChange={e => setEditSettings(prev => ({ ...prev, min_predicted_qty: parseInt(e.target.value) || 1 }))}
                style={{ width: '100%', padding: '0.4rem', border: '1px solid #ccc', borderRadius: 4 }}
              />
              <small style={{ color: '#999' }}>이 수량 이상 예측된 조합만 추천에 포함</small>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 600 }}>최소 출현 빈도</label>
              <input
                type="number" min={1} value={editSettings.min_frequency}
                onChange={e => setEditSettings(prev => ({ ...prev, min_frequency: parseInt(e.target.value) || 1 }))}
                style={{ width: '100%', padding: '0.4rem', border: '1px solid #ccc', borderRadius: 4 }}
              />
              <small style={{ color: '#999' }}>과거 데이터에서 이 횟수 이상 출현한 조합만 포함</small>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 600 }}>최소 SKU 수</label>
              <input
                type="number" min={1} value={editSettings.min_sku_count}
                onChange={e => setEditSettings(prev => ({ ...prev, min_sku_count: parseInt(e.target.value) || 1 }))}
                style={{ width: '100%', padding: '0.4rem', border: '1px solid #ccc', borderRadius: 4 }}
              />
              <small style={{ color: '#999' }}>합포장 기준 (2 = 2개 이상 SKU 조합만)</small>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 600 }}>유지 기간 (일)</label>
              <input
                type="number" min={1} value={editSettings.retention_days}
                onChange={e => setEditSettings(prev => ({ ...prev, retention_days: parseInt(e.target.value) || 1 }))}
                style={{ width: '100%', padding: '0.4rem', border: '1px solid #ccc', borderRadius: 4 }}
              />
              <small style={{ color: '#999' }}>미사용 프리패킹의 최대 보관 기간. 초과 시 해체 지시</small>
            </div>

            <button
              onClick={handleSaveSettings}
              style={{ width: '100%', padding: '0.5rem', backgroundColor: '#4CAF50', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 600 }}
            >설정 저장</button>
          </div>

          {allSettings.length > 0 && (
            <div>
              <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>현재 설정 목록</h3>
              <table style={{ borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    <th style={thStyle}>대상</th><th style={thStyle}>최소예측</th><th style={thStyle}>최소빈도</th><th style={thStyle}>최소SKU</th><th style={thStyle}>유지기간</th>
                  </tr>
                </thead>
                <tbody>
                  {allSettings.map(s => (
                    <tr key={s.vendor} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={tdStyle}>{s.vendor === '_default' ? '글로벌 기본값' : s.vendor}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{s.min_predicted_qty}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{s.min_frequency}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{s.min_sku_count}</td>
                      <td style={{ ...tdStyle, textAlign: 'center' }}>{s.retention_days}일</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = { padding: '0.5rem', textAlign: 'left', fontSize: '0.85rem', fontWeight: 600, whiteSpace: 'nowrap' };
const tdStyle: React.CSSProperties = { padding: '0.5rem', fontSize: '0.85rem', verticalAlign: 'top' };
const inputStyle: React.CSSProperties = { padding: '0.4rem', border: '1px solid #ccc', borderRadius: 4 };
const statCard: React.CSSProperties = {
  padding: '0.75rem 1rem', backgroundColor: '#f9f9f9', borderRadius: 8,
  border: '1px solid #e0e0e0', fontSize: '0.9rem', minWidth: 120,
};

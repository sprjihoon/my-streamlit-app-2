'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/Card';
import { Alert } from '@/components/Alert';
import { Loading } from '@/components/Loading';
import {
  getOutBasicRates,
  saveOutBasicRates,
  getOutExtraRates,
  saveOutExtraRates,
  getShippingZoneRates,
  saveShippingZoneRates,
  getMaterialRates,
  saveMaterialRates,
  OutBasicRate,
  OutExtraRate,
  ShippingZoneRate,
  MaterialRate,
} from '@/lib/api';

type TableType = 'out_basic' | 'out_extra' | 'shipping_zone' | 'material_rates';

const TABLE_INFO: Record<TableType, string> = {
  out_basic: '출고비 (SKU 구간)',
  out_extra: '추가 작업 단가',
  shipping_zone: '배송 요금 구간',
  material_rates: '부자재 요금표',
};

export default function RatesPage() {
  const [selectedTable, setSelectedTable] = useState<TableType>('out_basic');
  const [rateType, setRateType] = useState<'표준' | 'A'>('표준');

  // 데이터
  const [outBasicData, setOutBasicData] = useState<OutBasicRate[]>([]);
  const [outExtraData, setOutExtraData] = useState<OutExtraRate[]>([]);
  const [shippingZoneData, setShippingZoneData] = useState<ShippingZoneRate[]>([]);
  const [materialData, setMaterialData] = useState<MaterialRate[]>([]);

  // UI 상태
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [selectedTable, rateType]);

  async function loadData() {
    setLoading(true);
    setError(null);

    try {
      switch (selectedTable) {
        case 'out_basic':
          setOutBasicData(await getOutBasicRates());
          break;
        case 'out_extra':
          setOutExtraData(await getOutExtraRates());
          break;
        case 'shipping_zone':
          setShippingZoneData(await getShippingZoneRates(rateType));
          break;
        case 'material_rates':
          setMaterialData(await getMaterialRates());
          break;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '데이터 로드 실패');
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      switch (selectedTable) {
        case 'out_basic':
          await saveOutBasicRates(outBasicData);
          break;
        case 'out_extra':
          await saveOutExtraRates(outExtraData);
          break;
        case 'shipping_zone':
          await saveShippingZoneRates(shippingZoneData, rateType);
          break;
        case 'material_rates':
          await saveMaterialRates(materialData);
          break;
      }
      setSuccess('저장 완료!');
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장 실패');
    } finally {
      setSaving(false);
    }
  }

  function handleDownloadCsv() {
    let csvContent = '';
    let filename = '';

    switch (selectedTable) {
      case 'out_basic':
        csvContent = 'sku_group,단가\n' + outBasicData.map((r) => `${r.sku_group},${r.단가}`).join('\n');
        filename = 'out_basic_rates.csv';
        break;
      case 'out_extra':
        csvContent = '항목,단가\n' + outExtraData.map((r) => `${r.항목},${r.단가}`).join('\n');
        filename = 'out_extra_rates.csv';
        break;
      case 'shipping_zone':
        csvContent =
          '요금제,구간,len_min_cm,len_max_cm,요금\n' +
          shippingZoneData.map((r) => `${r.요금제},${r.구간},${r.len_min_cm},${r.len_max_cm},${r.요금}`).join('\n');
        filename = `shipping_zone_${rateType}_rates.csv`;
        break;
      case 'material_rates':
        csvContent = '항목,단가\n' + materialData.map((r) => `${r.항목},${r.단가}`).join('\n');
        filename = 'material_rates.csv';
        break;
    }

    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      const lines = text.split('\n').filter((line) => line.trim());
      
      if (lines.length < 2) {
        setError('CSV 파일에 데이터가 없습니다.');
        return;
      }

      try {
        switch (selectedTable) {
          case 'out_basic': {
            const data: OutBasicRate[] = lines.slice(1).map((line) => {
              const [sku_group, 단가] = line.split(',');
              return { sku_group: sku_group.trim(), 단가: parseInt(단가.trim()) };
            });
            setOutBasicData(data);
            break;
          }
          case 'out_extra': {
            const data: OutExtraRate[] = lines.slice(1).map((line) => {
              const [항목, 단가] = line.split(',');
              return { 항목: 항목.trim(), 단가: parseInt(단가.trim()) };
            });
            setOutExtraData(data);
            break;
          }
          case 'shipping_zone': {
            const data: ShippingZoneRate[] = lines.slice(1).map((line) => {
              const [요금제, 구간, len_min_cm, len_max_cm, 요금] = line.split(',');
              return {
                요금제: 요금제.trim(),
                구간: 구간.trim(),
                len_min_cm: parseInt(len_min_cm.trim()),
                len_max_cm: parseInt(len_max_cm.trim()),
                요금: parseInt(요금.trim()),
              };
            });
            setShippingZoneData(data);
            break;
          }
          case 'material_rates': {
            const data: MaterialRate[] = lines.slice(1).map((line) => {
              const [항목, 단가] = line.split(',');
              return { 항목: 항목.trim(), 단가: parseInt(단가.trim()) };
            });
            setMaterialData(data);
            break;
          }
        }
        setSuccess('CSV 파일 로드 완료! 저장 버튼을 클릭하여 DB에 반영하세요.');
      } catch (err) {
        setError('CSV 파싱 오류: ' + (err instanceof Error ? err.message : String(err)));
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  function updateOutBasic(index: number, field: keyof OutBasicRate, value: string | number) {
    const updated = [...outBasicData];
    if (field === '단가') {
      updated[index] = { ...updated[index], [field]: parseInt(String(value)) || 0 };
    } else {
      updated[index] = { ...updated[index], [field]: value };
    }
    setOutBasicData(updated);
  }

  function updateOutExtra(index: number, field: keyof OutExtraRate, value: string | number) {
    const updated = [...outExtraData];
    if (field === '단가') {
      updated[index] = { ...updated[index], [field]: parseInt(String(value)) || 0 };
    } else {
      updated[index] = { ...updated[index], [field]: value };
    }
    setOutExtraData(updated);
  }

  function updateShippingZone(index: number, field: keyof ShippingZoneRate, value: string | number) {
    const updated = [...shippingZoneData];
    if (['len_min_cm', 'len_max_cm', '요금'].includes(field)) {
      updated[index] = { ...updated[index], [field]: parseInt(String(value)) || 0 };
    } else {
      updated[index] = { ...updated[index], [field]: value };
    }
    setShippingZoneData(updated);
  }

  function updateMaterial(index: number, field: keyof MaterialRate, value: string | number) {
    const updated = [...materialData];
    if (field === '단가') {
      updated[index] = { ...updated[index], [field]: parseInt(String(value)) || 0 };
    } else {
      updated[index] = { ...updated[index], [field]: value };
    }
    setMaterialData(updated);
  }

  const inputStyle = {
    padding: '0.5rem',
    border: '1px solid #ddd',
    borderRadius: '4px',
    width: '100%',
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '2rem' }}>글로벌 요금표 관리</h1>

      {error && <Alert type="error" message={error} onClose={() => setError(null)} />}
      {success && <Alert type="success" message={success} onClose={() => setSuccess(null)} />}

      <Card>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label style={{ fontWeight: 500 }}>요금 테이블 선택:</label>
          <select
            value={selectedTable}
            onChange={(e) => setSelectedTable(e.target.value as TableType)}
            style={{
              padding: '0.5rem',
              border: '1px solid #ddd',
              borderRadius: '4px',
              minWidth: '200px',
            }}
          >
            {Object.entries(TABLE_INFO).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>

          {selectedTable === 'shipping_zone' && (
            <>
              <label style={{ fontWeight: 500, marginLeft: '1rem' }}>요금제:</label>
              <select
                value={rateType}
                onChange={(e) => setRateType(e.target.value as '표준' | 'A')}
                style={{
                  padding: '0.5rem',
                  border: '1px solid #ddd',
                  borderRadius: '4px',
                }}
              >
                <option value="표준">표준</option>
                <option value="A">A</option>
              </select>
            </>
          )}
        </div>
      </Card>

      <Card title={`${TABLE_INFO[selectedTable]} 수정`} style={{ marginTop: '1rem' }}>
        {loading ? (
          <Loading />
        ) : (
          <>
            {/* 출고비 테이블 */}
            {selectedTable === 'out_basic' && (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                      SKU 구간
                    </th>
                    <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>
                      단가 (원)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {outBasicData.map((row, idx) => (
                    <tr key={idx}>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <input
                          type="text"
                          value={row.sku_group}
                          onChange={(e) => updateOutBasic(idx, 'sku_group', e.target.value)}
                          style={inputStyle}
                        />
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <input
                          type="number"
                          value={row.단가}
                          onChange={(e) => updateOutBasic(idx, '단가', e.target.value)}
                          style={{ ...inputStyle, textAlign: 'right' }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {/* 추가 작업 단가 테이블 */}
            {selectedTable === 'out_extra' && (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                      항목
                    </th>
                    <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>
                      단가 (원)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {outExtraData.map((row, idx) => (
                    <tr key={idx}>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <input
                          type="text"
                          value={row.항목}
                          onChange={(e) => updateOutExtra(idx, '항목', e.target.value)}
                          style={inputStyle}
                        />
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <input
                          type="number"
                          value={row.단가}
                          onChange={(e) => updateOutExtra(idx, '단가', e.target.value)}
                          style={{ ...inputStyle, textAlign: 'right' }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {/* 배송 요금 구간 테이블 */}
            {selectedTable === 'shipping_zone' && (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                      요금제
                    </th>
                    <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                      구간
                    </th>
                    <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>
                      최소 길이 (cm)
                    </th>
                    <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>
                      최대 길이 (cm)
                    </th>
                    <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>
                      요금 (원)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {shippingZoneData.map((row, idx) => (
                    <tr key={idx}>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <input
                          type="text"
                          value={row.요금제}
                          onChange={(e) => updateShippingZone(idx, '요금제', e.target.value)}
                          style={inputStyle}
                        />
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <input
                          type="text"
                          value={row.구간}
                          onChange={(e) => updateShippingZone(idx, '구간', e.target.value)}
                          style={inputStyle}
                        />
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <input
                          type="number"
                          value={row.len_min_cm}
                          onChange={(e) => updateShippingZone(idx, 'len_min_cm', e.target.value)}
                          style={{ ...inputStyle, textAlign: 'right' }}
                        />
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <input
                          type="number"
                          value={row.len_max_cm}
                          onChange={(e) => updateShippingZone(idx, 'len_max_cm', e.target.value)}
                          style={{ ...inputStyle, textAlign: 'right' }}
                        />
                      </td>
                      <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                        <input
                          type="number"
                          value={row.요금}
                          onChange={(e) => updateShippingZone(idx, '요금', e.target.value)}
                          style={{ ...inputStyle, textAlign: 'right' }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {/* 부자재 요금표 테이블 */}
            {selectedTable === 'material_rates' && (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f5f5f5' }}>
                    <th style={{ padding: '0.5rem', textAlign: 'left', borderBottom: '2px solid #ddd' }}>
                      항목
                    </th>
                    <th style={{ padding: '0.5rem', textAlign: 'right', borderBottom: '2px solid #ddd' }}>
                      단가 (원)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {materialData.length === 0 ? (
                    <tr>
                      <td colSpan={2} style={{ padding: '1rem', textAlign: 'center', color: '#666' }}>
                        데이터가 없습니다. CSV 파일을 업로드하세요.
                      </td>
                    </tr>
                  ) : (
                    materialData.map((row, idx) => (
                      <tr key={idx}>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                          <input
                            type="text"
                            value={row.항목}
                            onChange={(e) => updateMaterial(idx, '항목', e.target.value)}
                            style={inputStyle}
                          />
                        </td>
                        <td style={{ padding: '0.5rem', borderBottom: '1px solid #eee' }}>
                          <input
                            type="number"
                            value={row.단가}
                            onChange={(e) => updateMaterial(idx, '단가', e.target.value)}
                            style={{ ...inputStyle, textAlign: 'right' }}
                          />
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            )}

            {/* 버튼들 */}
            <div style={{ marginTop: '2rem', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <button
                onClick={handleSave}
                disabled={saving}
                style={{
                  padding: '0.75rem 2rem',
                  backgroundColor: '#4CAF50',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: saving ? 'not-allowed' : 'pointer',
                }}
              >
                {saving ? '저장 중...' : '저장'}
              </button>

              <button
                onClick={handleDownloadCsv}
                style={{
                  padding: '0.75rem 2rem',
                  backgroundColor: '#2196F3',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                CSV 다운로드
              </button>

              <label
                style={{
                  padding: '0.75rem 2rem',
                  backgroundColor: '#ff9800',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  display: 'inline-block',
                }}
              >
                CSV 업로드
                <input type="file" accept=".csv" onChange={handleFileUpload} style={{ display: 'none' }} />
              </label>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}


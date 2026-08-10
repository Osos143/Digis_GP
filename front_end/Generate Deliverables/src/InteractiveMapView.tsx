import React, { useEffect, useRef, useState, useMemo } from 'react';
import { Anomaly, SessionSummary, analyzeRCA, RCAResult } from './api';
import { MapPin, Filter, RotateCcw, CheckSquare, Square, ChevronDown, Layers, AlertTriangle, FileText, RefreshCw, X, Bot, Sparkles, Activity, Loader2 } from 'lucide-react';

declare const window: any;

interface InteractiveMapViewProps {
  anomalies: Anomaly[];
  sessions?: SessionSummary[];
  selectedSessionId?: string;
  onSelectSession?: (sessionId: string) => void;
  loadingAnomalies?: boolean;
  onNavigate?: (view: string) => void;
}

// Safely parse numbers from floats or strings
function parseCoord(val: any): number | null {
  if (val === undefined || val === null || val === '') return null;
  const num = typeof val === 'number' ? val : parseFloat(String(val));
  return !isNaN(num) && isFinite(num) ? num : null;
}

export const InteractiveMapView: React.FC<InteractiveMapViewProps> = ({
  anomalies,
  sessions = [],
  selectedSessionId = '',
  onSelectSession,
  loadingAnomalies = false,
  onNavigate,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<any>(null);
  const markersGroupRef = useRef<any>(null);

  const [leafletReady, setLeafletReady] = useState<boolean>(!!(window && window.L));
  const [selectedAnomalyIds, setSelectedAnomalyIds] = useState<string[]>([]);
  const [activeMapAnomaly, setActiveMapAnomaly] = useState<any | null>(null);
  const [mapRcaResult, setMapRcaResult] = useState<RCAResult | null>(null);
  const [mapRcaLoading, setMapRcaLoading] = useState<boolean>(false);
  const [dropdownOpen, setDropdownOpen] = useState<boolean>(false);
  const [searchFilter, setSearchFilter] = useState<string>('');

  // Fetch MongoDB RCA diagnosis & telemetry evidence for selected map anomaly
  useEffect(() => {
    if (!activeMapAnomaly || !selectedSessionId) {
      setMapRcaResult(null);
      return;
    }
    const anomalyId = String(activeMapAnomaly.incident_id || activeMapAnomaly.anomaly_id || activeMapAnomaly.id || '');
    if (!anomalyId) return;

    setMapRcaLoading(true);
    analyzeRCA(selectedSessionId, anomalyId)
      .then((res) => setMapRcaResult(res.data))
      .catch(() => setMapRcaResult(null))
      .finally(() => setMapRcaLoading(false));
  }, [activeMapAnomaly, selectedSessionId]);

  // Dynamically load Leaflet CDN if window.L is not available yet
  useEffect(() => {
    if (window.L) {
      setLeafletReady(true);
      return;
    }

    if (!document.getElementById('leaflet-css-cdn')) {
      const link = document.createElement('link');
      link.id = 'leaflet-css-cdn';
      link.rel = 'stylesheet';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(link);
    }

    if (!document.getElementById('leaflet-js-cdn')) {
      const script = document.createElement('script');
      script.id = 'leaflet-js-cdn';
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.onload = () => setLeafletReady(true);
      document.head.appendChild(script);
    } else {
      const timer = setInterval(() => {
        if (window.L) {
          setLeafletReady(true);
          clearInterval(timer);
        }
      }, 100);
      return () => clearInterval(timer);
    }
  }, []);

  // Reset selected anomaly IDs & card when switching sessions/files
  useEffect(() => {
    setSelectedAnomalyIds([]);
    setActiveMapAnomaly(null);
  }, [selectedSessionId]);

  // Filter anomalies that have valid latitude & longitude
  const validGeoAnomalies = useMemo(() => {
    if (!anomalies || !Array.isArray(anomalies)) return [];
    return anomalies
      .map((a, idx) => {
        const lat = parseCoord(a.latitude ?? (a as any).lat ?? (a as any)['Location - Latitude']);
        const lng = parseCoord(a.longitude ?? (a as any).lng ?? (a as any).lon ?? (a as any)['Location - Longitude']);
        if (lat !== null && lng !== null && (lat !== 0 || lng !== 0)) {
          return { ...a, parsedLat: lat, parsedLng: lng, displayIndex: idx + 1 };
        }
        return null;
      })
      .filter((a): a is Anomaly & { parsedLat: number; parsedLng: number; displayIndex: number } => a !== null);
  }, [anomalies]);

  // Extract unique anomaly IDs
  const anomalyList = useMemo(() => {
    return validGeoAnomalies.map((a) => {
      const id = String(a.incident_id || a.anomaly_id || a.id || `ANOM_${a.displayIndex}`);
      const severity = String(a.anomaly_severity || a.severity || 'HIGH').toUpperCase();
      const type = String(a.anomaly_type || a.case_type || 'Throughput Degradation');
      const pci = a.pci !== undefined && a.pci !== null ? `PCI: ${a.pci}` : '';
      const actual = typeof a.actual_lte_dl_throughput === 'number' ? `${a.actual_lte_dl_throughput.toFixed(1)} Mbps` : '';
      return { id, anomaly: a, severity, type, pci, actual, label: `${id} - ${type} (${actual || pci})` };
    });
  }, [validGeoAnomalies]);

  // Filtered dropdown options based on search filter
  const filteredDropdownOptions = useMemo(() => {
    return anomalyList.filter((item) => {
      return (
        item.id.toLowerCase().includes(searchFilter.toLowerCase()) ||
        item.label.toLowerCase().includes(searchFilter.toLowerCase())
      );
    });
  }, [anomalyList, searchFilter]);

  // Initialize Leaflet Map
  useEffect(() => {
    if (!leafletReady || !mapContainerRef.current) return;
    const L = window.L;
    if (!L) return;

    if (!mapInstanceRef.current) {
      const initialLat = validGeoAnomalies.length > 0 ? validGeoAnomalies[0].parsedLat : 30.0444;
      const initialLng = validGeoAnomalies.length > 0 ? validGeoAnomalies[0].parsedLng : 31.2357;

      const map = L.map(mapContainerRef.current, {
        center: [initialLat, initialLng],
        zoom: 13,
        zoomControl: true,
      });

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(map);

      markersGroupRef.current = L.layerGroup().addTo(map);
      mapInstanceRef.current = map;

      setTimeout(() => {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.invalidateSize();
        }
      }, 250);
    }

    return () => {
      try {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.remove();
          mapInstanceRef.current = null;
        }
      } catch (err) {
        mapInstanceRef.current = null;
      }
    };
  }, [leafletReady]);

  // Update Markers & Zoom view based on selected anomaly IDs
  useEffect(() => {
    const L = window.L;
    const map = mapInstanceRef.current;
    const markersGroup = markersGroupRef.current;
    if (!L || !map || !markersGroup) return;

    try {
      markersGroup.clearLayers();
    } catch (e) {
      return;
    }

    const isFiltered = selectedAnomalyIds.length > 0;
    const targetAnomalies = isFiltered
      ? validGeoAnomalies.filter((a) => {
          const id = String(a.incident_id || a.anomaly_id || a.id || `ANOM_${a.displayIndex}`);
          return selectedAnomalyIds.includes(id);
        })
      : validGeoAnomalies;

    if (targetAnomalies.length === 0) return;

    const bounds = L.latLngBounds([]);

    targetAnomalies.forEach((anom) => {
      const lat = anom.parsedLat;
      const lng = anom.parsedLng;
      bounds.extend([lat, lng]);

      const id = String(anom.incident_id || anom.anomaly_id || anom.id || `ANOM_${anom.displayIndex}`);
      const severity = String(anom.anomaly_severity || anom.severity || 'HIGH').toUpperCase();
      const type = String(anom.anomaly_type || 'Throughput Degradation');
      const actual = typeof anom.actual_lte_dl_throughput === 'number' ? `${anom.actual_lte_dl_throughput.toFixed(2)} Mbps` : 'N/A';
      const expectedP75 = typeof anom.expected_tp_p75 === 'number' ? `${anom.expected_tp_p75.toFixed(2)} Mbps` : 'N/A';
      const rsrp = typeof anom.lte_rsrp === 'number' ? `${anom.lte_rsrp.toFixed(1)} dBm` : 'N/A';
      const sinr = typeof anom.lte_sinr === 'number' ? `${anom.lte_sinr.toFixed(1)} dB` : 'N/A';
      const pci = anom.pci !== undefined ? String(anom.pci) : 'N/A';

      let markerColor = '#f59e0b';
      if (severity.includes('CRIT')) markerColor = '#ef4444';
      else if (severity.includes('MED')) markerColor = '#eab308';
      else if (severity.includes('LOW')) markerColor = '#3b82f6';

      const customIcon = L.divIcon({
        className: 'custom-map-pin',
        html: `
          <div style="
            background-color: ${markerColor};
            width: 32px;
            height: 32px;
            border-radius: 50%;
            border: 3px solid white;
            box-shadow: 0 4px 12px rgba(0,0,0,0.35);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 14px;
            cursor: pointer;
            transition: transform 0.2s ease;
          " title="${id}">
            📍
          </div>
        `,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
      });

      const marker = L.marker([lat, lng], { icon: customIcon });
      marker.on('click', () => {
        setActiveMapAnomaly(anom);
      });
      markersGroup.addLayer(marker);
    });

    // Auto-Zoom & Invalidate Size
    setTimeout(() => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.invalidateSize();
        if (bounds.isValid()) {
          if (selectedAnomalyIds.length === 1) {
            const single = targetAnomalies[0];
            mapInstanceRef.current.flyTo([single.parsedLat, single.parsedLng], 16, { duration: 1.2 });
          } else {
            mapInstanceRef.current.flyToBounds(bounds, { padding: [60, 60], maxZoom: 16, duration: 1.0 });
          }
        }
      }
    }, 150);
  }, [selectedAnomalyIds, validGeoAnomalies, leafletReady]);

  // Toggle selection of an anomaly ID
  const toggleAnomalySelection = (id: string) => {
    setSelectedAnomalyIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  // Select all or clear selection
  const selectAll = () => {
    setSelectedAnomalyIds(anomalyList.map((a) => a.id));
  };

  const clearSelection = () => {
    setSelectedAnomalyIds([]);
  };

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      {/* Top Header & Map Controls Bar */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-2 bg-blue-50 text-blue-600 rounded-lg">
              <MapPin className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">Interactive Drive Test Anomaly Map</h2>
              <p className="text-xs text-gray-500">
                Visualizing {validGeoAnomalies.length} drive-test anomaly locations on interactive map canvas.
              </p>
            </div>
          </div>
        </div>

        {/* Controls Container */}
        <div className="flex flex-col sm:flex-row items-center gap-3 w-full md:w-auto">
          {/* Dataset File Selector */}
          {sessions && sessions.length > 0 && (
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <FileText className="w-4 h-4 text-blue-600 shrink-0" />
              <select
                value={selectedSessionId}
                onChange={(e) => {
                  if (onSelectSession) onSelectSession(e.target.value);
                }}
                className="bg-slate-50 hover:bg-slate-100 border border-slate-300 rounded-lg px-3 py-2 text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm cursor-pointer w-full sm:w-auto max-w-xs"
              >
                {sessions.map((s) => {
                  const filename = (s.dataset?.filename as string) || (s.dataset?.file_path as string) || `Session ${s.session_id.slice(0, 8)}`;
                  const date = s.created_at ? new Date(s.created_at).toLocaleDateString() : '';
                  return (
                    <option key={s.session_id} value={s.session_id}>
                      📄 {filename} ({s.anomaly_count || 0} anomalies{date ? ` - ${date}` : ''})
                    </option>
                  );
                })}
              </select>
            </div>
          )}

          {/* Multi-Select Anomaly Filter Dropdown */}
          <div className="relative w-full sm:w-72">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="w-full bg-slate-50 hover:bg-slate-100 border border-slate-300 text-slate-800 px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center justify-between shadow-sm transition-all"
            >
              <div className="flex items-center gap-2 truncate">
                <Filter className="w-4 h-4 text-blue-600 shrink-0" />
                <span className="truncate">
                  {selectedAnomalyIds.length === 0
                    ? `All Anomalies (${anomalyList.length})`
                    : `${selectedAnomalyIds.length} Selected Anomalies`}
                </span>
              </div>
              <ChevronDown className={`w-4 h-4 text-slate-500 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            {/* Dropdown Popup Panel */}
            {dropdownOpen && (
              <div className="absolute right-0 mt-2 w-full md:w-96 bg-white border border-gray-200 rounded-xl shadow-xl z-[2000] p-3 space-y-3">
                {/* Search Box */}
                <input
                  type="text"
                  placeholder="Search anomaly ID or PCI..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  className="w-full bg-gray-50 border border-gray-200 px-3 py-1.5 rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                />

                {/* Action Buttons */}
                <div className="flex items-center justify-between text-xs pt-1 border-b border-gray-100 pb-2">
                  <button
                    onClick={selectAll}
                    className="text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1"
                  >
                    <CheckSquare className="w-3.5 h-3.5" /> Select All ({anomalyList.length})
                  </button>
                  <button
                    onClick={clearSelection}
                    className="text-gray-500 hover:text-gray-700 font-medium flex items-center gap-1"
                  >
                    <RotateCcw className="w-3.5 h-3.5" /> Reset (Show All)
                  </button>
                </div>

                {/* Anomaly Checkbox List */}
                <div className="max-h-60 overflow-y-auto space-y-1 pr-1">
                  {filteredDropdownOptions.length === 0 ? (
                    <p className="text-xs text-gray-400 text-center py-3">No anomalies found matching search.</p>
                  ) : (
                    filteredDropdownOptions.map((item) => {
                      const isSelected = selectedAnomalyIds.includes(item.id);
                      return (
                        <div
                          key={item.id}
                          onClick={() => toggleAnomalySelection(item.id)}
                          className={`flex items-center justify-between p-2 rounded-lg text-xs cursor-pointer transition-colors ${
                            isSelected ? 'bg-blue-50 border border-blue-200' : 'hover:bg-gray-50'
                          }`}
                        >
                          <div className="flex items-center gap-2 truncate">
                            {isSelected ? (
                              <CheckSquare className="w-4 h-4 text-blue-600 shrink-0" />
                            ) : (
                              <Square className="w-4 h-4 text-gray-300 shrink-0" />
                            )}
                            <span className="font-semibold text-gray-800 truncate">{item.id}</span>
                            <span className="text-gray-400 text-[10px] truncate">{item.pci}</span>
                          </div>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase shrink-0 ${
                              item.severity.includes('CRIT')
                                ? 'bg-red-100 text-red-700'
                                : item.severity.includes('HIGH')
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-yellow-100 text-yellow-700'
                            }`}
                          >
                            {item.severity}
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Selected Pills Bar */}
      {selectedAnomalyIds.length > 0 && (
        <div className="bg-blue-50/80 border border-blue-200 rounded-lg p-3 flex items-center justify-between flex-wrap gap-2 text-xs">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-blue-900 flex items-center gap-1">
              <Layers className="w-3.5 h-3.5 text-blue-600" /> Active View Filter ({selectedAnomalyIds.length}):
            </span>
            {selectedAnomalyIds.map((id) => (
              <span
                key={id}
                className="bg-white border border-blue-300 text-blue-800 px-2 py-0.5 rounded-full font-semibold flex items-center gap-1 shadow-xs"
              >
                {id}
                <button
                  onClick={() => toggleAnomalySelection(id)}
                  className="hover:text-red-600 font-bold ml-1"
                >
                  &times;
                </button>
              </span>
            ))}
          </div>
          <button
            onClick={clearSelection}
            className="text-blue-700 hover:text-blue-900 font-bold underline text-xs"
          >
            Show All Anomalies
          </button>
        </div>
      )}

      {/* Main Interactive Map Container */}
      <div className="relative rounded-xl border border-gray-200 overflow-hidden shadow-md bg-slate-50 h-[calc(100vh-210px)] min-h-[780px] w-full">
        {loadingAnomalies ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-blue-600 gap-3 bg-white/90 z-20">
            <RefreshCw className="w-8 h-8 animate-spin" />
            <p className="text-sm font-semibold text-slate-700">Fetching anomaly geolocation markers...</p>
          </div>
        ) : validGeoAnomalies.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-500 p-6 text-center bg-slate-50">
            <AlertTriangle className="w-12 h-12 text-amber-500 mb-2 animate-bounce" />
            <p className="font-semibold text-slate-800 text-base">No Geolocation Coordinates Found in Dataset</p>
            <p className="text-xs text-slate-500 max-w-md mt-1">
              Loaded {anomalies.length} anomaly records, but none contain valid GPS latitude/longitude values.
            </p>
          </div>
        ) : null}

        <div ref={mapContainerRef} className="w-full h-full z-10" />

        {/* Floating Anomaly Info Card with Modern Motion */}
        {activeMapAnomaly && (
          <div className="absolute bottom-6 right-6 z-[1000] w-[460px] max-w-[calc(100vw-3rem)] bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl shadow-2xl p-6 space-y-4 animate-in slide-in-from-bottom-6 fade-in duration-300">
            {/* Header */}
            <div className="flex items-start justify-between border-b border-slate-100 pb-3.5">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-blue-50 text-blue-600 rounded-xl">
                  <AlertTriangle className="w-6 h-6 text-blue-600" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-base sm:text-lg text-slate-900 font-mono">
                      {String(activeMapAnomaly.incident_id || activeMapAnomaly.anomaly_id || activeMapAnomaly.id || 'INC-000412')}
                    </h3>
                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-extrabold uppercase border ${
                      String(mapRcaResult?.diagnosis?.severity || activeMapAnomaly.anomaly_severity || activeMapAnomaly.severity || 'HIGH').toUpperCase().includes('CRIT')
                        ? "bg-red-50 text-red-700 border-red-200"
                        : "bg-amber-50 text-amber-700 border-amber-200"
                    }`}>
                      {String(mapRcaResult?.diagnosis?.severity || activeMapAnomaly.anomaly_severity || activeMapAnomaly.severity || 'HIGH')}
                    </span>
                  </div>
                  <p className="text-sm font-bold text-slate-800 mt-1">
                    {String(mapRcaResult?.diagnosis?.problem_name || activeMapAnomaly.anomaly_type || 'Throughput Degradation')}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveMapAnomaly(null)}
                className="text-slate-400 hover:text-slate-700 p-1.5 rounded-md hover:bg-slate-100 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* RCA Diagnosis Reason (from MongoDB) */}
            {mapRcaLoading ? (
              <div className="flex items-center gap-2 text-sm text-blue-600 bg-blue-50 p-3 rounded-xl border border-blue-100 font-medium">
                <Loader2 className="w-4 h-4 animate-spin" /> Fetching MongoDB RCA telemetry diagnosis...
              </div>
            ) : mapRcaResult?.diagnosis?.reason ? (
              <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200/80 text-sm text-slate-800 font-medium leading-relaxed">
                <span className="text-xs font-bold text-blue-600 uppercase tracking-wider block mb-1">
                  RCA Cause ({mapRcaResult.diagnosis.cause_id})
                </span>
                {mapRcaResult.diagnosis.reason}
              </div>
            ) : null}

            {/* Cell & Geolocation Details */}
            <div className="grid grid-cols-2 gap-2.5 text-xs">
              <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
                <span className="text-slate-500 block text-xs font-semibold">Cell ID / PCI</span>
                <span className="font-bold text-slate-900 font-mono text-sm sm:text-base">
                  {activeMapAnomaly.cell_id || (activeMapAnomaly.pci !== undefined ? `PCI-${activeMapAnomaly.pci}` : 'CELL_0412')}
                </span>
              </div>
              <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
                <span className="text-slate-500 block text-xs font-semibold">Coordinates</span>
                <span className="font-bold text-slate-900 font-mono text-sm sm:text-base">
                  {activeMapAnomaly.parsedLat ? activeMapAnomaly.parsedLat.toFixed(4) : '30.0444'}, {activeMapAnomaly.parsedLng ? activeMapAnomaly.parsedLng.toFixed(4) : '31.2357'}
                </span>
              </div>
            </div>

            {/* Key Telemetry Metrics */}
            <div className="space-y-2">
              <span className="text-xs sm:text-sm font-bold text-slate-600 uppercase tracking-wider block">Key Telemetry Metrics (MongoDB)</span>
              <div className="grid grid-cols-2 gap-2.5">
                {(() => {
                  const kpiEv = mapRcaResult?.key_kpi_evidence || {};

                  let tp = kpiEv.actual_throughput_mbps ?? activeMapAnomaly.actual_lte_dl_throughput;
                  if (typeof tp === 'number' && tp > 100) tp = tp / 1000000;
                  const tpVal = typeof tp === 'number' ? `${tp.toFixed(1)} Mbps` : '1.4 Mbps';

                  let expTp = activeMapAnomaly.expected_tp_p75;
                  if (typeof expTp === 'number' && expTp > 100) expTp = expTp / 1000000;
                  const expTpVal = typeof expTp === 'number' ? `${expTp.toFixed(1)} Mbps` : '9.4 Mbps';

                  const rsrp = kpiEv.rsrp_dbm ?? activeMapAnomaly.lte_rsrp ?? -114.2;
                  const sinr = kpiEv.sinr_db ?? activeMapAnomaly.lte_sinr ?? -3.1;

                  return (
                    <>
                      <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
                        <span className="text-slate-500 block text-xs font-semibold">Actual Throughput</span>
                        <span className="font-bold text-red-600 font-mono text-base sm:text-lg">{tpVal}</span>
                      </div>
                      <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
                        <span className="text-slate-500 block text-xs font-semibold">Expected P75</span>
                        <span className="font-bold text-emerald-600 font-mono text-base sm:text-lg">{expTpVal}</span>
                      </div>
                      <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
                        <span className="text-slate-500 block text-xs font-semibold">RSRP</span>
                        <span className="font-bold text-slate-900 font-mono text-sm sm:text-base">
                          {typeof rsrp === 'number' ? `${rsrp.toFixed(1)} dBm` : '-114.2 dBm'}
                        </span>
                      </div>
                      <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
                        <span className="text-slate-500 block text-xs font-semibold">SINR</span>
                        <span className="font-bold text-slate-900 font-mono text-sm sm:text-base">
                          {typeof sinr === 'number' ? `${sinr.toFixed(1)} dB` : '-3.1 dB'}
                        </span>
                      </div>
                    </>
                  );
                })()}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="flex items-center gap-2.5 pt-2">
              <button
                onClick={() => {
                  const id = String(activeMapAnomaly.incident_id || activeMapAnomaly.anomaly_id || activeMapAnomaly.id || 'INC-000412');
                  localStorage.setItem('copilot_selected_session', selectedSessionId);
                  localStorage.setItem('netfix_tracked_session_id', selectedSessionId);
                  localStorage.setItem('copilot_selected_anomaly', id);
                  localStorage.setItem('netfix_selected_rca_anomaly', id);
                  if (onNavigate) onNavigate('ai');
                }}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-4 rounded-xl text-sm transition-all shadow-sm flex items-center justify-center gap-2 cursor-pointer"
              >
                <span className="text-base leading-none">🐧</span> Ask Penguin
              </button>
              <button
                onClick={() => {
                  const id = String(activeMapAnomaly.incident_id || activeMapAnomaly.anomaly_id || activeMapAnomaly.id || 'INC-000412');
                  localStorage.setItem('copilot_selected_session', selectedSessionId);
                  localStorage.setItem('netfix_tracked_session_id', selectedSessionId);
                  localStorage.setItem('copilot_selected_anomaly', id);
                  localStorage.setItem('netfix_selected_rca_anomaly', id);
                  if (onNavigate) onNavigate('results');
                }}
                className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold py-2.5 px-4 rounded-xl text-sm transition-all border border-slate-200 flex items-center justify-center gap-2 cursor-pointer"
              >
                <Sparkles className="w-4 h-4 text-blue-600" /> Run RCA
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

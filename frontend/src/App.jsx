import { useState, useEffect, useRef } from 'react'
import './index.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

function RiskBadge({ classification, size = "md" }) {
  const colors = {
    HIGH: "bg-red-600 text-white",
    MEDIUM: "bg-yellow-500 text-black",
    LOW: "bg-green-600 text-white",
    CLEARED: "bg-green-600 text-white",
  }
  const sizes = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-3 py-1 text-sm",
    lg: "px-4 py-2 text-base"
  }
  return (
    <span className={`rounded-full font-semibold ${colors[classification] || "bg-gray-600 text-white"} ${sizes[size]}`}>
      {classification}
    </span>
  )
}

function NetworkGraph({ members }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (!canvasRef.current || !members?.length) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()

    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)

    const width = rect.width
    const height = rect.height

    const centerX = width / 2
    const centerY = height / 2
    const radius = members.length === 1 ? 0 : Math.min(width, height) * 0.3

    const nodes = members.map((m, i) => {
      if (members.length === 1) {
        return { ...m, x: centerX, y: centerY }
      }
      const angle = (2 * Math.PI * i) / members.length - Math.PI / 2
      return {
        ...m,
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      }
    })

    // Background
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, width, height)

    // Grid lines for effect
    ctx.strokeStyle = '#1e293b'
    ctx.lineWidth = 1
    for (let i = 0; i < width; i += 30) {
      ctx.beginPath()
      ctx.moveTo(i, 0)
      ctx.lineTo(i, height)
      ctx.stroke()
    }
    for (let i = 0; i < height; i += 30) {
      ctx.beginPath()
      ctx.moveTo(0, i)
      ctx.lineTo(width, i)
      ctx.stroke()
    }

    // Draw edges (connections between nodes)
    if (nodes.length > 1) {
      ctx.strokeStyle = '#3b82f6'
      ctx.lineWidth = 2
      ctx.globalAlpha = 0.3
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          ctx.beginPath()
          ctx.moveTo(nodes[i].x, nodes[i].y)
          ctx.lineTo(nodes[j].x, nodes[j].y)
          ctx.stroke()
        }
      }
      ctx.globalAlpha = 1
    }

    // Draw nodes
    nodes.forEach((node, idx) => {
      const risk = node.fraud_risk_score || 0
      const color = risk > 0.8 ? '#dc2626' : risk > 0.5 ? '#f59e0b' : '#22c55e'
      const nodeRadius = 20 + risk * 20

      // Glow effect
      const gradient = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, nodeRadius * 2)
      gradient.addColorStop(0, color + '40')
      gradient.addColorStop(1, 'transparent')
      ctx.fillStyle = gradient
      ctx.fillRect(node.x - nodeRadius * 2, node.y - nodeRadius * 2, nodeRadius * 4, nodeRadius * 4)

      ctx.beginPath()
      if (node.is_excluded) {
        // Diamond shape for excluded
        ctx.moveTo(node.x, node.y - nodeRadius)
        ctx.lineTo(node.x + nodeRadius, node.y)
        ctx.lineTo(node.x, node.y + nodeRadius)
        ctx.lineTo(node.x - nodeRadius, node.y)
        ctx.closePath()
      } else {
        ctx.arc(node.x, node.y, nodeRadius, 0, 2 * Math.PI)
      }
      ctx.fillStyle = color
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 3
      ctx.stroke()

      // Node label
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 10px sans-serif'
      ctx.textAlign = 'center'
      const shortName = (node.facility_name || '').substring(0, 15)
      ctx.fillText(shortName + (node.facility_name?.length > 15 ? '...' : ''), node.x, node.y + nodeRadius + 15)
    })

  }, [members])

  return (
    <canvas
      ref={canvasRef}
      className="w-full rounded-lg border border-slate-700"
      style={{ height: '300px' }}
    />
  )
}

function GeoMap({ communityId, members }) {
  const canvasRef = useRef(null)
  const [geoData, setGeoData] = useState(null)

  useEffect(() => {
    if (!communityId) return
    fetch(`${API_URL}/community/${communityId}/geo`)
      .then(r => r.ok ? r.json() : null)
      .then(setGeoData)
      .catch(() => {})
  }, [communityId])

  useEffect(() => {
    if (!canvasRef.current || !geoData?.facilities?.length) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()

    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)

    const width = rect.width
    const height = rect.height

    // Background
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, width, height)

    const facilities = geoData.facilities
    if (!facilities.length) return

    // Calculate bounds
    const lats = facilities.map(f => f.lat)
    const lons = facilities.map(f => f.lon)
    const minLat = Math.min(...lats) - 0.02
    const maxLat = Math.max(...lats) + 0.02
    const minLon = Math.min(...lons) - 0.02
    const maxLon = Math.max(...lons) + 0.02

    const scaleX = width / (maxLon - minLon)
    const scaleY = height / (maxLat - minLat)

    // Draw grid
    ctx.strokeStyle = '#1e293b'
    ctx.lineWidth = 1
    for (let i = 0; i < width; i += 40) {
      ctx.beginPath()
      ctx.moveTo(i, 0)
      ctx.lineTo(i, height)
      ctx.stroke()
    }
    for (let i = 0; i < height; i += 40) {
      ctx.beginPath()
      ctx.moveTo(0, i)
      ctx.lineTo(width, i)
      ctx.stroke()
    }

    // Draw facilities
    facilities.forEach(f => {
      const x = (f.lon - minLon) * scaleX
      const y = height - (f.lat - minLat) * scaleY
      const risk = f.fraud_risk_score || 0
      const color = f.is_excluded ? '#dc2626' : risk > 0.7 ? '#f59e0b' : risk > 0.4 ? '#eab308' : '#22c55e'
      const radius = 8 + risk * 12

      // Glow
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius * 2)
      gradient.addColorStop(0, color + '60')
      gradient.addColorStop(1, 'transparent')
      ctx.fillStyle = gradient
      ctx.fillRect(x - radius * 2, y - radius * 2, radius * 4, radius * 4)

      // Point
      ctx.beginPath()
      ctx.arc(x, y, radius, 0, 2 * Math.PI)
      ctx.fillStyle = color
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.stroke()
    })

    // Legend
    ctx.fillStyle = '#94a3b8'
    ctx.font = '11px sans-serif'
    ctx.fillText('Geographic Distribution', 10, 20)

  }, [geoData])

  if (!geoData?.facilities?.length) {
    return (
      <div className="h-48 bg-slate-800/50 rounded-lg flex items-center justify-center text-slate-500 text-sm">
        No geographic data available
      </div>
    )
  }

  return (
    <div>
      <canvas ref={canvasRef} className="w-full rounded-lg border border-slate-700" style={{ height: '200px' }} />
      <div className="mt-2 text-xs text-slate-500 text-center">
        {geoData.facilities.length} facilities mapped
      </div>
    </div>
  )
}

function OwnershipGraph({ communityId }) {
  const canvasRef = useRef(null)
  const [ownerData, setOwnerData] = useState(null)

  useEffect(() => {
    if (!communityId) return
    fetch(`${API_URL}/community/${communityId}/ownership`)
      .then(r => r.ok ? r.json() : null)
      .then(setOwnerData)
      .catch(() => {})
  }, [communityId])

  useEffect(() => {
    if (!canvasRef.current || !ownerData?.nodes?.length) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()

    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)

    const width = rect.width
    const height = rect.height

    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, width, height)

    const nodes = ownerData.nodes
    const edges = ownerData.edges

    // Separate owners and facilities
    const owners = nodes.filter(n => n.type === 'owner')
    const facilities = nodes.filter(n => n.type === 'facility')

    // Position owners on left, facilities on right
    const nodePositions = {}

    owners.forEach((n, i) => {
      nodePositions[n.id] = {
        x: 80,
        y: 40 + (i * (height - 80) / Math.max(owners.length - 1, 1)),
        ...n
      }
    })

    facilities.forEach((n, i) => {
      nodePositions[n.id] = {
        x: width - 80,
        y: 40 + (i * (height - 80) / Math.max(facilities.length - 1, 1)),
        ...n
      }
    })

    // Draw edges
    ctx.strokeStyle = '#3b82f6'
    ctx.lineWidth = 1.5
    ctx.globalAlpha = 0.4
    edges.forEach(e => {
      const source = nodePositions[e.source]
      const target = nodePositions[e.target]
      if (source && target) {
        ctx.beginPath()
        ctx.moveTo(source.x, source.y)
        ctx.lineTo(target.x, target.y)
        ctx.stroke()
      }
    })
    ctx.globalAlpha = 1

    // Draw nodes
    Object.values(nodePositions).forEach(node => {
      const isOwner = node.type === 'owner'
      const radius = isOwner ? 10 : 14
      const color = isOwner ? '#8b5cf6' : (node.excluded ? '#dc2626' : node.risk > 0.5 ? '#f59e0b' : '#22c55e')

      ctx.beginPath()
      if (isOwner) {
        // Square for owners
        ctx.rect(node.x - radius, node.y - radius, radius * 2, radius * 2)
      } else {
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
      }
      ctx.fillStyle = color
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.stroke()

      // Label
      ctx.fillStyle = '#e2e8f0'
      ctx.font = '9px sans-serif'
      ctx.textAlign = isOwner ? 'right' : 'left'
      ctx.fillText(node.label, isOwner ? node.x - 15 : node.x + 18, node.y + 3)
    })

    // Legend
    ctx.fillStyle = '#94a3b8'
    ctx.font = '11px sans-serif'
    ctx.textAlign = 'left'
    ctx.fillText('Ownership Network', 10, 20)

  }, [ownerData])

  if (!ownerData?.nodes?.length || ownerData.nodes.length < 2) {
    return (
      <div className="h-48 bg-slate-800/50 rounded-lg flex items-center justify-center text-slate-500 text-sm">
        No ownership connections found
      </div>
    )
  }

  const ownerCount = ownerData.nodes.filter(n => n.type === 'owner').length
  const facilityCount = ownerData.nodes.filter(n => n.type === 'facility').length

  return (
    <div>
      <canvas ref={canvasRef} className="w-full rounded-lg border border-slate-700" style={{ height: '200px' }} />
      <div className="mt-2 flex justify-center gap-4 text-xs text-slate-500">
        <span><span className="text-purple-400">■</span> {ownerCount} Owners</span>
        <span><span className="text-green-400">●</span> {facilityCount} Facilities</span>
      </div>
    </div>
  )
}

function ShapPanel({ communityId }) {
  const [shapData, setShapData] = useState(null)

  useEffect(() => {
    if (!communityId) return
    fetch(`${API_URL}/community/${communityId}/shap`)
      .then(r => r.ok ? r.json() : null)
      .then(setShapData)
      .catch(() => {})
  }, [communityId])

  if (!shapData?.features?.length) {
    return (
      <div className="h-48 bg-slate-800/50 rounded-lg flex items-center justify-center text-slate-500 text-sm">
        Loading SHAP values...
      </div>
    )
  }

  const maxAbs = Math.max(...shapData.features.map(f => Math.abs(f.shap_value)))

  return (
    <div className="space-y-2">
      <div className="text-xs text-slate-500 mb-3">Why did the model flag this community?</div>
      {shapData.features.slice(0, 6).map((f, i) => {
        const width = Math.abs(f.shap_value) / maxAbs * 100
        const isPositive = f.shap_value > 0
        return (
          <div key={i} className="flex items-center gap-2">
            <div className="w-32 text-xs text-slate-400 truncate text-right">{f.feature}</div>
            <div className="flex-1 h-4 bg-slate-800 rounded relative overflow-hidden">
              <div
                className={`absolute h-full ${isPositive ? 'bg-red-500 left-1/2' : 'bg-green-500 right-1/2'}`}
                style={{ width: `${width / 2}%` }}
              />
              <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-600" />
            </div>
            <div className={`w-12 text-xs ${isPositive ? 'text-red-400' : 'text-green-400'}`}>
              {isPositive ? '+' : ''}{f.shap_value.toFixed(2)}
            </div>
          </div>
        )
      })}
      <div className="flex justify-between text-xs text-slate-600 mt-2 px-32">
        <span>Lowers risk</span>
        <span>Raises risk</span>
      </div>
    </div>
  )
}

function SimilarNetworks({ communityId, onInvestigate }) {
  const [similarData, setSimilarData] = useState(null)

  useEffect(() => {
    if (!communityId) return
    fetch(`${API_URL}/community/${communityId}/similar?limit=4`)
      .then(r => r.ok ? r.json() : null)
      .then(setSimilarData)
      .catch(() => {})
  }, [communityId])

  if (!similarData?.similar?.length) {
    return (
      <div className="h-32 bg-slate-800/50 rounded-lg flex items-center justify-center text-slate-500 text-sm">
        No similar networks found
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="text-xs text-slate-500 mb-2">Networks with similar risk profiles</div>
      {similarData.similar.map((s, i) => (
        <div
          key={i}
          className="flex items-center justify-between p-2 bg-slate-800/50 rounded hover:bg-slate-800 cursor-pointer transition-colors"
          onClick={() => onInvestigate({ type: 'community', value: s.community_id })}
        >
          <div className="flex items-center gap-3">
            <span className="text-white font-medium text-sm">#{s.community_id}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded ${
              s.risk_label === 'HIGH' ? 'bg-red-900/50 text-red-400' :
              s.risk_label === 'MEDIUM' ? 'bg-yellow-900/50 text-yellow-400' :
              'bg-green-900/50 text-green-400'
            }`}>{s.risk_label}</span>
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-400">
            <span>{s.member_count} facilities</span>
            <span className="text-red-400">{s.excluded_count} excluded</span>
            <span className="text-slate-500">{(s.similarity_score * 100).toFixed(0)}% match</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function MemberTable({ members }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-800 text-slate-300">
          <tr>
            <th className="px-4 py-2">NPI</th>
            <th className="px-4 py-2">Facility Name</th>
            <th className="px-4 py-2">Risk Score</th>
            <th className="px-4 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {members.map((m, i) => (
            <tr key={i} className={`border-b border-slate-700 ${m.is_excluded ? 'bg-red-900/20' : ''}`}>
              <td className="px-4 py-2 font-mono text-xs">{m.npi}</td>
              <td className="px-4 py-2">{m.facility_name}</td>
              <td className="px-4 py-2">
                <span className={`font-semibold ${m.fraud_risk_score > 0.8 ? 'text-red-400' : m.fraud_risk_score > 0.5 ? 'text-yellow-400' : 'text-green-400'}`}>
                  {m.fraud_risk_score?.toFixed(3) || '0.000'}
                </span>
              </td>
              <td className="px-4 py-2">
                {m.is_excluded ? <span className="text-red-400 font-semibold">EXCLUDED</span> : <span className="text-green-400">Active</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RedFlags({ flags }) {
  if (!flags?.details) return null

  // Check for DOJ prosecution matches
  const dojMatches = flags.doj_prosecution_matches || []

  return (
    <div className="space-y-3">
      {/* DOJ Alert - show prominently if found */}
      {dojMatches.length > 0 && (
        <div className="bg-red-900/40 border border-red-600 rounded-lg p-4 mb-4">
          <div className="flex items-center gap-2 text-red-400 font-bold mb-2">
            <span className="text-xl">!</span>
            DOJ PROSECUTION RECORD FOUND
          </div>
          {dojMatches.map((match, i) => (
            <div key={i} className="text-sm text-red-200 mt-2">
              <div className="font-semibold">{match.facility_name}</div>
              <div className="text-red-300 whitespace-pre-wrap">{match.research_summary}</div>
            </div>
          ))}
        </div>
      )}

      {/* Regular red flags */}
      {Object.entries(flags.details).map(([key, value]) => (
        <div key={key} className="flex items-start gap-2">
          <span className={value.triggered ? "text-red-400" : "text-green-400"}>
            {value.triggered ? "+" : "-"}
          </span>
          <div>
            <span className="font-medium capitalize">{key.replace(/_/g, ' ')}</span>
            <p className="text-sm text-slate-400">{value.detail}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function Dossier({ dossier }) {
  if (!dossier) return null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">
          {dossier.community_id ? `Community ${dossier.community_id}` : `NPI ${dossier.seed_npi}`}
        </h2>
        <RiskBadge classification={dossier.classification} size="lg" />
      </div>

      <div className="grid grid-cols-4 gap-4">
        <div className="bg-slate-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-white">{dossier.member_count}</div>
          <div className="text-xs text-slate-400">Facilities</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-red-400">{dossier.excluded_count}</div>
          <div className="text-xs text-slate-400">Excluded</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-yellow-400">{dossier.flags_triggered}/{dossier.total_flags}</div>
          <div className="text-xs text-slate-400">Red Flags</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-white">{dossier.avg_risk_score?.toFixed(3)}</div>
          <div className="text-xs text-slate-400">Avg Risk</div>
        </div>
      </div>

      {dossier.red_flags?.false_positive_warnings?.length > 0 && (
        <div className="bg-yellow-900/20 border border-yellow-700 rounded-lg p-4">
          <div className="text-yellow-400 font-semibold mb-1">Potential False Positive</div>
          <p className="text-sm text-yellow-200">{dossier.red_flags.false_positive_warnings[0]}</p>
        </div>
      )}

      <div>
        <h3 className="text-lg font-semibold text-white mb-3">Red Flags Analysis</h3>
        <RedFlags flags={dossier.red_flags || dossier} />
      </div>

      <div>
        <h3 className="text-lg font-semibold text-white mb-3">Network Members</h3>
        <MemberTable members={dossier.members || []} />
      </div>

      {dossier.narrative && (
        <div className="bg-slate-800 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-white mb-3">Investigation Report</h3>
          <div className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed prose prose-invert prose-sm max-w-none">
            {dossier.narrative}
          </div>
        </div>
      )}

      {dossier.hypotheses && (
        <details className="bg-slate-800 rounded-lg" open>
          <summary className="p-4 cursor-pointer text-white font-medium">Agent Hypotheses</summary>
          <div className="px-4 pb-4 text-sm text-slate-300 whitespace-pre-wrap">{dossier.hypotheses}</div>
        </details>
      )}

      {dossier.evaluation && (
        <details className="bg-slate-800 rounded-lg" open>
          <summary className="p-4 cursor-pointer text-white font-medium">Evidence Evaluation</summary>
          <div className="px-4 pb-4 text-sm text-slate-300 whitespace-pre-wrap">{dossier.evaluation}</div>
        </details>
      )}
    </div>
  )
}

function SearchPage({ onInvestigate, stats }) {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchType, setSearchType] = useState('npi') // 'community', 'npi', 'region'
  const [communities, setCommunities] = useState([])
  const [searchResults, setSearchResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [topLoading, setTopLoading] = useState(true)

  // Load top communities on mount
  useEffect(() => {
    async function loadTop() {
      try {
        const res = await fetch(`${API_URL}/communities/top?n=10`)
        if (res.ok) {
          const data = await res.json()
          setCommunities(data.communities || [])
        }
      } catch (e) {
        console.error('Failed to load communities:', e)
      }
      setTopLoading(false)
    }
    loadTop()
  }, [])

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setLoading(true)
    setSearchResults(null)

    try {
      if (searchType === 'npi' || /^\d{10}$/.test(searchQuery.trim())) {
        // Direct NPI investigation
        onInvestigate({ type: 'npi', value: searchQuery.trim() })
      } else if (searchType === 'community' && /^\d+$/.test(searchQuery.trim())) {
        // Direct community investigation
        onInvestigate({ type: 'community', value: parseInt(searchQuery.trim()) })
      } else {
        // Search by name/region
        const res = await fetch(`${API_URL}/search?q=${encodeURIComponent(searchQuery)}&limit=20`)
        if (res.ok) {
          const data = await res.json()
          setSearchResults(data)
        }
      }
    } catch (e) {
      console.error('Search failed:', e)
    }
    setLoading(false)
  }

  const handleQuickFilter = async (filter) => {
    setLoading(true)
    try {
      let url = `${API_URL}/communities/top?n=20`
      if (filter !== 'all') {
        url = `${API_URL}/communities?region=${filter}&limit=20`
      }
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        setCommunities(data.communities || [])
      }
    } catch (e) {
      console.error('Filter failed:', e)
    }
    setLoading(false)
  }

  return (
    <div className="max-w-5xl mx-auto">
      {/* Hero Section */}
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold text-white mb-3">Healthcare Provider Investigation</h1>
        <p className="text-slate-400 max-w-2xl mx-auto">
          Enter a provider NPI number, community ID, or facility name to run a comprehensive fraud risk investigation using AI-powered network analysis.
        </p>
      </div>

      {/* Search controls */}
      <div className="bg-slate-900 rounded-xl p-6 mb-8 border border-slate-800">
        <div className="flex gap-4 mb-4">
          <select
            value={searchType}
            onChange={(e) => setSearchType(e.target.value)}
            className="px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
          >
            <option value="npi">NPI Number</option>
            <option value="community">Community ID</option>
            <option value="region">Facility Name / City</option>
          </select>
          <input
            type="text"
            placeholder={
              searchType === 'npi' ? "Enter 10-digit NPI (e.g., 1234567890)..." :
              searchType === 'community' ? "Enter community ID..." :
              "Enter facility name or city..."
            }
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="flex-1 px-6 py-3 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={handleSearch}
            disabled={loading}
            className="px-8 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white rounded-lg font-semibold transition-colors"
          >
            {loading ? 'Searching...' : 'Investigate'}
          </button>
        </div>

        {/* Quick filters */}
        <div className="flex gap-2 items-center">
          <span className="text-slate-500 text-sm">Quick filters:</span>
          {['all', 'miami', 'tampa', 'orlando', 'jacksonville'].map(f => (
            <button
              key={f}
              onClick={() => handleQuickFilter(f)}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm capitalize transition-colors border border-slate-700"
            >
              {f === 'all' ? 'Highest Risk' : f}
            </button>
          ))}
        </div>
      </div>

      {/* Search results */}
      {searchResults && (
        <div className="bg-slate-900 rounded-xl p-6 mb-8 border border-slate-800">
          <h3 className="text-lg font-semibold text-white mb-4">Search Results</h3>
          {searchResults.facilities?.length > 0 ? (
            <table className="w-full text-sm">
              <thead className="text-slate-400 border-b border-slate-700">
                <tr>
                  <th className="text-left py-2 px-2">NPI</th>
                  <th className="text-left py-2 px-2">Facility</th>
                  <th className="text-left py-2 px-2">Risk Score</th>
                  <th className="text-left py-2 px-2">Status</th>
                  <th className="text-left py-2 px-2"></th>
                </tr>
              </thead>
              <tbody className="text-white">
                {searchResults.facilities.map(f => (
                  <tr key={f.npi} className="border-b border-slate-800 hover:bg-slate-800/50">
                    <td className="py-3 px-2 font-mono text-xs">{f.npi}</td>
                    <td className="py-3 px-2">{f.facility_name}</td>
                    <td className="py-3 px-2">
                      <span className={`font-semibold ${f.fraud_risk_score > 0.8 ? 'text-red-400' : f.fraud_risk_score > 0.5 ? 'text-yellow-400' : 'text-green-400'}`}>
                        {f.fraud_risk_score?.toFixed(3)}
                      </span>
                    </td>
                    <td className="py-3 px-2">
                      {f.is_excluded ? <span className="text-red-400 text-xs font-medium">EXCLUDED</span> : <span className="text-green-400 text-xs">Active</span>}
                    </td>
                    <td className="py-3 px-2">
                      <button
                        onClick={() => onInvestigate({ type: 'npi', value: f.npi })}
                        className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium"
                      >
                        Investigate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-slate-400">No facilities found matching your search.</p>
          )}
        </div>
      )}

      {/* High Risk Communities */}
      <div className="bg-slate-900 rounded-xl overflow-hidden border border-slate-800">
        <div className="px-6 py-4 border-b border-slate-800 flex justify-between items-center">
          <div>
            <h3 className="text-lg font-semibold text-white">High Risk Provider Networks</h3>
            <p className="text-sm text-slate-500">Communities flagged by ML risk scoring and network analysis</p>
          </div>
          {!topLoading && <span className="text-sm text-slate-500">{communities.length} communities</span>}
        </div>
        <table className="w-full">
          <thead className="bg-slate-800/50">
            <tr className="text-left text-slate-400 text-sm">
              <th className="px-6 py-3">Community</th>
              <th className="px-6 py-3">Risk Level</th>
              <th className="px-6 py-3">Providers</th>
              <th className="px-6 py-3">Excluded</th>
              <th className="px-6 py-3">Red Flags</th>
              <th className="px-6 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {communities.map(c => (
              <tr key={c.community_id} className="border-t border-slate-800 hover:bg-slate-800/30 transition-colors">
                <td className="px-6 py-4 text-white font-semibold">#{c.community_id}</td>
                <td className="px-6 py-4"><RiskBadge classification={c.risk_label} size="sm" /></td>
                <td className="px-6 py-4 text-white">{c.member_count}</td>
                <td className="px-6 py-4 text-red-400 font-medium">{c.excluded_count}</td>
                <td className="px-6 py-4 text-yellow-400">{c.flags_triggered}/5</td>
                <td className="px-6 py-4">
                  <button
                    onClick={() => onInvestigate({ type: 'community', value: c.community_id })}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
                  >
                    Investigate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function InvestigationPage({ target, onBack, onInvestigate }) {
  const [dossier, setDossier] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [useFullAnalysis, setUseFullAnalysis] = useState(true)
  const [pipelineStep, setPipelineStep] = useState(0)
  const [showExport, setShowExport] = useState(false)

  useEffect(() => {
    async function runInvestigation() {
      setLoading(true)
      setError(null)
      setDossier(null)
      setPipelineStep(0)

      // Simulate pipeline steps for visual feedback
      const steps = useFullAnalysis ? [
        'Loading provider data',
        'Building ownership network',
        'Checking exclusion databases',
        'Running red flag analysis',
        'Cross-referencing DOJ records',
        'Generating AI hypotheses',
        'Evaluating evidence',
        'Writing investigation report'
      ] : [
        'Loading provider data',
        'Running quick analysis',
        'Checking red flags'
      ]

      // Progress animation
      let stepIndex = 0
      const stepInterval = setInterval(() => {
        if (stepIndex < steps.length - 1) {
          stepIndex++
          setPipelineStep(stepIndex)
        }
      }, useFullAnalysis ? 4000 : 300)

      try {
        let url
        if (target.type === 'community') {
          url = `${API_URL}/investigate/community/${target.value}?full_analysis=${useFullAnalysis}`
        } else {
          url = `${API_URL}/investigate/npi/${target.value}?full_analysis=${useFullAnalysis}`
        }

        const res = await fetch(url, { method: 'POST' })
        clearInterval(stepInterval)
        setPipelineStep(steps.length - 1)

        if (!res.ok) {
          const err = await res.json()
          throw new Error(err.detail || 'Investigation failed')
        }
        const data = await res.json()
        setDossier(data)
      } catch (e) {
        clearInterval(stepInterval)
        setError(e.message)
      }
      setLoading(false)
    }
    runInvestigation()
  }, [target, useFullAnalysis])

  const handleExport = (format) => {
    if (!dossier) return
    const content = format === 'json'
      ? JSON.stringify(dossier, null, 2)
      : `# Investigation Report\n\n${dossier.narrative || 'No narrative available'}\n\n## Members\n${(dossier.members || []).map(m => `- ${m.facility_name} (NPI: ${m.npi})`).join('\n')}`

    const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `investigation-${target.value}.${format === 'json' ? 'json' : 'md'}`
    a.click()
    setShowExport(false)
  }

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <button onClick={onBack} className="text-slate-400 hover:text-white flex items-center gap-2 transition-colors">
          <span>&larr;</span> Back to Search
        </button>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input
              type="checkbox"
              checked={useFullAnalysis}
              onChange={(e) => setUseFullAnalysis(e.target.checked)}
              className="rounded bg-slate-800 border-slate-600"
            />
            Full AI Analysis
          </label>
          {dossier && (
            <div className="relative">
              <button
                onClick={() => setShowExport(!showExport)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-sm border border-slate-700"
              >
                Export Report
              </button>
              {showExport && (
                <div className="absolute right-0 mt-2 bg-slate-800 rounded-lg shadow-xl border border-slate-700 overflow-hidden z-10">
                  <button onClick={() => handleExport('json')} className="block w-full px-4 py-2 text-left text-sm text-white hover:bg-slate-700">Export as JSON</button>
                  <button onClick={() => handleExport('md')} className="block w-full px-4 py-2 text-left text-sm text-white hover:bg-slate-700">Export as Markdown</button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <div className="bg-slate-900 rounded-xl p-8 border border-slate-800">
          <div className="text-xl text-white font-semibold mb-6 text-center">
            Running Investigation Pipeline
          </div>
          <div className="max-w-md mx-auto space-y-3">
            {(useFullAnalysis ? [
              'Loading provider data',
              'Building ownership network',
              'Checking exclusion databases',
              'Running red flag analysis',
              'Cross-referencing DOJ records',
              'Generating AI hypotheses',
              'Evaluating evidence',
              'Writing investigation report'
            ] : [
              'Loading provider data',
              'Running quick analysis',
              'Checking red flags'
            ]).map((step, i) => (
              <div key={i} className={`flex items-center gap-3 p-3 rounded-lg transition-all ${
                i < pipelineStep ? 'bg-green-900/30 text-green-400' :
                i === pipelineStep ? 'bg-blue-900/30 text-blue-400' :
                'bg-slate-800/50 text-slate-500'
              }`}>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  i < pipelineStep ? 'bg-green-600 text-white' :
                  i === pipelineStep ? 'bg-blue-600 text-white animate-pulse' :
                  'bg-slate-700 text-slate-400'
                }`}>
                  {i < pipelineStep ? '✓' : i + 1}
                </div>
                <span className="font-medium">{step}</span>
                {i === pipelineStep && <span className="ml-auto text-xs opacity-75">Processing...</span>}
              </div>
            ))}
          </div>
          <div className="text-center mt-6 text-sm text-slate-500">
            {useFullAnalysis ? 'Full AI analysis typically takes 30-60 seconds' : 'Quick analysis takes 2-5 seconds'}
          </div>
        </div>
      ) : error ? (
        <div className="bg-red-900/20 border border-red-700 rounded-xl p-6">
          <div className="text-red-400 font-semibold mb-2">Investigation Failed</div>
          <p className="text-red-200">{error}</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Visualizations Row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Network Graph */}
            <div className="bg-slate-900 rounded-xl p-5 border border-slate-800">
              <h3 className="text-sm font-semibold text-white mb-3">Community Network</h3>
              <NetworkGraph members={dossier?.members || []} />
              <div className="mt-3 flex gap-3 text-xs text-slate-500 justify-center">
                <span><span className="text-green-500">*</span> Low</span>
                <span><span className="text-yellow-500">*</span> Med</span>
                <span><span className="text-red-500">*</span> High</span>
              </div>
            </div>

            {/* SHAP Explainability */}
            <div className="bg-slate-900 rounded-xl p-5 border border-slate-800">
              <h3 className="text-sm font-semibold text-white mb-3">ML Model Explanation (SHAP)</h3>
              <ShapPanel communityId={dossier?.community_id} />
            </div>

            {/* Similar Networks */}
            <div className="bg-slate-900 rounded-xl p-5 border border-slate-800">
              <h3 className="text-sm font-semibold text-white mb-3">Similar Networks</h3>
              <SimilarNetworks communityId={dossier?.community_id} onInvestigate={onInvestigate} />
            </div>
          </div>

          {/* Dossier */}
          <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
            <Dossier dossier={dossier} />
          </div>
        </div>
      )}
    </div>
  )
}

function AboutPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Hero */}
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-white mb-4">How Provera Works</h1>
        <p className="text-xl text-slate-400 max-w-3xl mx-auto">
          An AI-powered fraud detection system that analyzes provider networks, ownership structures, and billing patterns to identify potential Medicare fraud rings.
        </p>
      </div>

      {/* Architecture Overview */}
      <div className="bg-slate-900 rounded-xl p-8 border border-slate-800">
        <h2 className="text-2xl font-bold text-white mb-6">System Architecture</h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="bg-slate-800/50 rounded-lg p-6">
            <div className="w-12 h-12 bg-blue-600 rounded-lg flex items-center justify-center text-white text-xl mb-4">1</div>
            <h3 className="text-lg font-semibold text-white mb-2">Data Ingestion</h3>
            <p className="text-slate-400 text-sm">
              We integrate data from CMS NPPES, Provider Enrollment, LEIE exclusion lists, Florida SunBiz corporate records, and Medicare billing statistics.
            </p>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-6">
            <div className="w-12 h-12 bg-blue-600 rounded-lg flex items-center justify-center text-white text-xl mb-4">2</div>
            <h3 className="text-lg font-semibold text-white mb-2">Graph Construction</h3>
            <p className="text-slate-400 text-sm">
              Facilities are linked through shared ownership, addresses, phone numbers, and billing relationships to create a provider network graph with 11,000+ nodes.
            </p>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-6">
            <div className="w-12 h-12 bg-blue-600 rounded-lg flex items-center justify-center text-white text-xl mb-4">3</div>
            <h3 className="text-lg font-semibold text-white mb-2">AI Investigation</h3>
            <p className="text-slate-400 text-sm">
              An AI agent generates hypotheses, evaluates evidence, and produces investigation reports with actionable recommendations.
            </p>
          </div>
        </div>
      </div>

      {/* ML Pipeline */}
      <div className="bg-slate-900 rounded-xl p-8 border border-slate-800">
        <h2 className="text-2xl font-bold text-white mb-6">Machine Learning Pipeline</h2>
        <div className="space-y-6">
          <div className="flex gap-6 items-start">
            <div className="w-24 shrink-0 text-right">
              <span className="text-blue-400 font-semibold">Features</span>
            </div>
            <div className="flex-1">
              <p className="text-slate-300 mb-2">We extract 30+ features from each provider including:</p>
              <div className="flex flex-wrap gap-2">
                {['Network Centrality', 'Community Size', 'Ownership Concentration', 'Billing Patterns', 'Entity Age', 'Exclusion History', 'Address Sharing', 'Phone Clustering'].map(f => (
                  <span key={f} className="px-3 py-1 bg-slate-800 rounded-full text-xs text-slate-300">{f}</span>
                ))}
              </div>
            </div>
          </div>
          <div className="flex gap-6 items-start">
            <div className="w-24 shrink-0 text-right">
              <span className="text-blue-400 font-semibold">Model</span>
            </div>
            <div className="flex-1">
              <p className="text-slate-300">
                <strong>XGBoost Classifier</strong> trained on LEIE exclusion labels with class balancing. Achieves 0.91 ROC-AUC and 85% precision at top 100 predictions.
              </p>
            </div>
          </div>
          <div className="flex gap-6 items-start">
            <div className="w-24 shrink-0 text-right">
              <span className="text-blue-400 font-semibold">Explainability</span>
            </div>
            <div className="flex-1">
              <p className="text-slate-300">
                <strong>SHAP values</strong> provide feature importance explanations for each prediction, enabling investigators to understand why a provider was flagged.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* AI Agent */}
      <div className="bg-slate-900 rounded-xl p-8 border border-slate-800">
        <h2 className="text-2xl font-bold text-white mb-6">AI Investigation Agent</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <h3 className="text-lg font-semibold text-white mb-3">Capabilities</h3>
            <ul className="space-y-2 text-slate-300">
              <li className="flex items-start gap-2">
                <span className="text-green-400 mt-1">+</span>
                <span>Generates fraud hypotheses based on network patterns</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400 mt-1">+</span>
                <span>Evaluates evidence for and against each hypothesis</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400 mt-1">+</span>
                <span>Cross-references DOJ prosecution records</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400 mt-1">+</span>
                <span>Identifies false positive signals (e.g., hospital systems)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400 mt-1">+</span>
                <span>Produces actionable investigation briefs</span>
              </li>
            </ul>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white mb-3">Red Flag Checks</h3>
            <ul className="space-y-2 text-slate-300">
              <li className="flex items-start gap-2">
                <span className="text-red-400 mt-1">1</span>
                <span>Ownership concentration (3+ facilities, same owner)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-400 mt-1">2</span>
                <span>Shared address with different entity names</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-400 mt-1">3</span>
                <span>Connection to LEIE-excluded providers</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-400 mt-1">4</span>
                <span>Billing deviation (&gt;2σ from state median)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-400 mt-1">5</span>
                <span>Shared phone numbers across entities</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      {/* Scalability */}
      <div className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 rounded-xl p-8 border border-blue-800">
        <h2 className="text-2xl font-bold text-white mb-4">Scalable to All 50 States</h2>
        <p className="text-slate-300 mb-6">
          While this prototype focuses on Florida (the highest-fraud state), the architecture is designed to scale nationally:
        </p>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="text-center">
            <div className="text-3xl font-bold text-blue-400 mb-1">11,000+</div>
            <div className="text-slate-400">Florida Providers</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-blue-400 mb-1">1.2M+</div>
            <div className="text-slate-400">National Providers</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-blue-400 mb-1">Cloud-Native</div>
            <div className="text-slate-400">AWS/GCP Ready</div>
          </div>
        </div>
      </div>

      {/* Validation */}
      <div className="bg-slate-900 rounded-xl p-8 border border-slate-800">
        <h2 className="text-2xl font-bold text-white mb-6">Validation Results</h2>
        <div className="grid md:grid-cols-2 gap-8">
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">Golden Set Performance</h3>
            <div className="bg-slate-800 rounded-lg p-6">
              <div className="text-4xl font-bold text-green-400 mb-2">7/7</div>
              <div className="text-slate-400">Correct classifications on curated test cases</div>
              <div className="mt-4 text-sm text-slate-500">
                Includes shell company networks, legitimate hospital systems, PE-backed chains, and established nonprofits.
              </div>
            </div>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">DOJ Case Validation</h3>
            <div className="bg-slate-800 rounded-lg p-6">
              <div className="text-4xl font-bold text-yellow-400 mb-2">7/8</div>
              <div className="text-slate-400">DOJ-prosecuted facilities found in database</div>
              <div className="mt-4 text-sm text-slate-500">
                System now cross-references DOJ prosecution records to catch behavioral fraud patterns not visible in ownership data.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Limitations */}
      <div className="bg-slate-900 rounded-xl p-8 border border-slate-800">
        <h2 className="text-2xl font-bold text-white mb-4">Known Limitations</h2>
        <div className="text-slate-300 space-y-3">
          <p>
            <strong>Structural vs. Behavioral Fraud:</strong> Provera excels at detecting structural fraud (shell companies, co-located entities, shared ownership) but cannot detect behavioral fraud (kickbacks, phantom billing, referral steering) without claims-level data.
          </p>
          <p>
            <strong>Data Freshness:</strong> Public datasets may lag behind real-time provider changes. Production deployment would require more frequent data updates.
          </p>
          <p>
            <strong>False Positives:</strong> Large healthcare systems (HCA, Kindred) may trigger flags due to legitimate corporate structure. The AI agent includes false positive detection to mitigate this.
          </p>
        </div>
      </div>
    </div>
  )
}

function App() {
  const [page, setPage] = useState('search')
  const [investigationTarget, setInvestigationTarget] = useState(null)
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetch(`${API_URL}/stats`).then(r => r.ok && r.json()).then(setStats).catch(() => {})
  }, [])

  const handleInvestigate = (target) => {
    setInvestigationTarget(target)
    setPage('investigate')
  }

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="bg-slate-900 border-b border-slate-800">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3 cursor-pointer" onClick={() => setPage('search')}>
              <svg className="w-9 h-9" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                {/* Shield background */}
                <path d="M20 2L4 10V19C4 29.5 11 36.5 20 38C29 36.5 36 29.5 36 19V10L20 2Z" fill="url(#shieldGradient)" stroke="#3B82F6" strokeWidth="1.5"/>
                {/* Network nodes */}
                <circle cx="20" cy="14" r="3" fill="#fff"/>
                <circle cx="12" cy="22" r="2.5" fill="#fff"/>
                <circle cx="28" cy="22" r="2.5" fill="#fff"/>
                <circle cx="16" cy="30" r="2" fill="#fff"/>
                <circle cx="24" cy="30" r="2" fill="#fff"/>
                {/* Network edges */}
                <path d="M20 14L12 22M20 14L28 22M12 22L16 30M28 22L24 30M16 30L24 30" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" opacity="0.7"/>
                {/* Checkmark */}
                <path d="M14 22L18 26L26 16" stroke="#22C55E" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                <defs>
                  <linearGradient id="shieldGradient" x1="20" y1="2" x2="20" y2="38" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#1E40AF"/>
                    <stop offset="1" stopColor="#3B82F6"/>
                  </linearGradient>
                </defs>
              </svg>
              <div>
                <h1 className="text-xl font-bold text-white tracking-tight">Provera</h1>
                <p className="text-xs text-slate-500">Medicare Fraud Detection</p>
              </div>
            </div>
            <nav className="flex gap-6">
              <button
                onClick={() => setPage('search')}
                className={`text-sm font-medium transition-colors ${page === 'search' || page === 'investigate' ? 'text-white' : 'text-slate-400 hover:text-white'}`}
              >
                Investigation
              </button>
              <button
                onClick={() => setPage('about')}
                className={`text-sm font-medium transition-colors ${page === 'about' ? 'text-white' : 'text-slate-400 hover:text-white'}`}
              >
                How It Works
              </button>
            </nav>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-slate-500">Prototype</span>
            <span className="px-2 py-1 bg-green-900/50 text-green-400 rounded text-xs font-medium">Florida Dataset</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="px-6 py-10">
        {page === 'search' && <SearchPage onInvestigate={handleInvestigate} stats={stats} />}
        {page === 'investigate' && <InvestigationPage target={investigationTarget} onBack={() => setPage('search')} onInvestigate={handleInvestigate} />}
        {page === 'about' && <AboutPage />}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 mt-16">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="flex justify-between items-start">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-6 h-6" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M20 2L4 10V19C4 29.5 11 36.5 20 38C29 36.5 36 29.5 36 19V10L20 2Z" fill="#3B82F6"/>
                  <circle cx="20" cy="14" r="2.5" fill="#fff"/>
                  <circle cx="13" cy="22" r="2" fill="#fff"/>
                  <circle cx="27" cy="22" r="2" fill="#fff"/>
                  <path d="M20 14L13 22M20 14L27 22" stroke="#fff" strokeWidth="1.5" opacity="0.7"/>
                  <path d="M14 21L18 25L26 15" stroke="#22C55E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <span className="font-semibold text-white">Provera</span>
              </div>
              <p className="text-sm text-slate-500 max-w-md">
                AI-powered Medicare fraud detection using network analysis, machine learning, and large language models.
              </p>
            </div>
            <div className="text-right text-sm text-slate-500">
              <p>Capstone Project</p>
              <p className="text-slate-600">George Washington University</p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App

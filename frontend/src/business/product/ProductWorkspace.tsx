import { useLocation } from 'react-router-dom'
import BusinessSurface from '../BusinessSurface'
import NewProductProject from './NewProductProject'
import ProductProjectDetail from './ProductProjectDetail'
import ProductProjects from './ProductProjects'
import ProductOutputs from './ProductOutputs'
import ProductKnowledge from './ProductKnowledge'
import TenderOpportunities from './TenderOpportunities'
import './product-division.css'

export default function ProductWorkspace({ feature }: { feature: string }) {
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const task = params.get('task')
  return <BusinessSurface key={`${location.pathname}${location.search}`}>
    {feature === 'documents' && (task ? <ProductProjectDetail id={task} artifact={params.get('artifact') || ''} /> : params.get('view') === 'projects' ? <ProductProjects view="projects" /> : <NewProductProject />)}
    {feature === 'opportunities' && <TenderOpportunities />}
    {feature === 'knowledge' && <ProductKnowledge />}
    {feature === 'outputs' && <ProductOutputs />}
  </BusinessSurface>
}

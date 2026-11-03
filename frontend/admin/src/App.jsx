import {Navigate, Route, Routes, useLocation} from "react-router-dom";
import {useAuth} from './context/AuthContext.jsx';
import Layout from './components/Layout.jsx';
import {Loading} from './components/PageState.jsx';
import LoginPage from './pages/LoginPage.jsx';
import AssessmentsPage from './pages/AssessmentsPage.jsx';
import NewAssessmentPage from './pages/NewAssessmentPage.jsx';
import AssessmentLayout from './pages/AssessmentLayout.jsx';
import OverviewTab from './pages/OverviewTab.jsx';
import QuestionsTab from './pages/QuestionsTab.jsx';
import ParticipantsTab from './pages/ParticipantsTab.jsx';
import ResultsTab from './pages/ResultsTab.jsx';
import AttemptPage from './pages/AttemptPage.jsx';
import UsersPage from './pages/UsersPage.jsx';
import NotFoundPage from './pages/NotFoundPage.jsx';

function Protected({children, adminOnly = false}) {
    const {user, loading} = useAuth();
    const location = useLocation();
    if (loading) return <Loading full/>;
    if (!user) return <Navigate to="/login" replace state={{from: location.pathname}}/>;
    if (adminOnly && user.role !== 'admin') return <Navigate to="/assessments" replace/>;
    return children;
}

export default function App() {
    const {user, loading} = useAuth();
    return(
        <Routes>
            <Route path="/login" element={ loading? <Loading full/> : user ? <Navigate to="/assessments" replace/> : <LoginPage/> }/>
             <Route path="/" element={<Protected><Layout/></Protected>}>
             <Route path="assessments" element={<AssessmentsPage/>}/>
             <Route path="assessments/new" element={<NewAssessmentPage/>}/>
             <Route path="assessments/:id" element={<AssessmentLayout/>}>
                <Route index element={<OverviewTab/>}/>
                <Route path="questions" element={<QuestionsTab/>}/>
                <Route path="participants" element={<ParticipantsTab/>}/>
                <Route path="results" element={<ResultsTab/>}/>
             </Route>
             <Route path="assessments/:attemptId" element={<AttemptPage/>}/>
             <Route path="users" element={<Protected adminOnly><UsersPage/></Protected>}/>
             <Route path="*" element={<NotFoundPage/>}/>
            </Route>
        </Routes>
    );
}
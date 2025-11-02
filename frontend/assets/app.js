// Smooth scrolling for in-page anchors
document.addEventListener('DOMContentLoaded', () => {
    // Prefill from URL params if present (index page)
    try {
        const params = new URLSearchParams(window.location.search);
        const dest = params.get('dest');
        const days = params.get('days');
        const budget = params.get('budget');
        const people = params.get('people');
        if (dest) {
            const d = document.getElementById('destination'); if (d) d.value = decodeURIComponent(dest);
        }
        if (days) { const el = document.getElementById('days'); if (el) el.value = Number(days) || ''; }
        if (budget) { const el = document.getElementById('budget'); if (el) el.value = Number(budget) || ''; }
        if (people) { const el = document.getElementById('people'); if (el) el.value = Number(people) || 1; }
        if (dest || days || budget || people) {
            const home = document.getElementById('tripForm');
            if (home) home.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    } catch {}
});

document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', (e) => {
        const id = a.getAttribute('href');
        if (id.length > 1) {
            e.preventDefault();
            const el = document.querySelector(id);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

const tripForm = document.getElementById('tripForm');
const outputDiv = document.getElementById('trip-plan-output');
const submitButton = document.getElementById('submit-button');
const buttonText = document.getElementById('button-text');
const buttonSpinner = document.getElementById('button-spinner');

const iconMap = {
    sightseeing: '<i data-lucide="camera" class="w-5 h-5 mr-3 text-purple-400"></i>',
    food: '<i data-lucide="utensils" class="w-5 h-5 mr-3 text-orange-400"></i>',
    activity: '<i data-lucide="map-pin" class="w-5 h-5 mr-3 text-green-400"></i>',
    default: '<i data-lucide="star" class="w-5 h-5 mr-3 text-gray-400"></i>'
};

tripForm.addEventListener('submit', async function(event) {
    event.preventDefault();
    console.log('📋 Form submitted');
    setLoadingState(true);

    const formData = new FormData(tripForm);
    
    const peopleCount = parseInt(formData.get('people'), 10) || 1;

    const tripDetails = {
        destination: formData.get('destination'),
        days: parseInt(formData.get('days'), 10),
        budget: parseFloat(formData.get('budget')),
        people: peopleCount,
        travelerType: peopleCount === 1 ? 'solo' : (peopleCount === 2 ? 'couple' : 'group'),
        hotelArea: formData.get('hotelArea') || 'any',
        vegOnly: (formData.get('vegOnly') || 'false') === 'true',
        mealsPerDay: parseInt(formData.get('mealsPerDay') || '2', 10)
    };
    
    console.log('✅ Received Trip Details:', tripDetails);
    
    let itinerary; 

    try {
        console.log('🚀 Sending request to backend...');
        const response = await fetch('http://127.0.0.1:5000/plan-trip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(tripDetails),
        });
        
        console.log('📡 Response status:', response.status, response.statusText);
        
        if (!response.ok) {
            // Try to parse structured error for minimum budget
            let err; 
            try { 
                err = await response.json(); 
                console.error('❌ Error response:', err);
            } catch (e) {
                err = {};
                console.error('❌ Could not parse error response');
            }
            
            if (response.status === 422 && err && err.error === 'budget_too_low') {
                alert(err.message || 'Entered budget is below the minimum estimate.');
                setLoadingState(false);
                return;
            }
            throw new Error(`HTTP error! status: ${response.status} - ${err.message || response.statusText}`);
        }

        itinerary = await response.json(); 
        console.log('✅ Received itinerary:', itinerary);
        console.log('✅ Itinerary keys:', Object.keys(itinerary));
        console.log('✅ Itinerary ID:', itinerary.itinerary_id);

        // Persist itinerary and redirect to dedicated plan page
        try {
            sessionStorage.setItem('tripster_last_itinerary', JSON.stringify(itinerary));
            console.log('✅ Saved to sessionStorage');
        } catch (e) {
            console.warn('Could not save to sessionStorage:', e);
        }
        
        const id = itinerary.itinerary_id || itinerary.id || '';
        console.log('📋 Extracted ID:', id);
        console.log('📍 Current location:', window.location.href);
        
        // Redirect immediately - don't wait
        const redirectUrl = `plan.html${id ? `?id=${encodeURIComponent(id)}` : ''}`;
        console.log('🔄 Redirecting to:', redirectUrl);
        console.log('🔄 Full URL will be:', new URL(redirectUrl, window.location.origin).href);
        
        // Force redirect
        try {
            window.location.href = redirectUrl;
        } catch (e) {
            console.error('❌ Redirect failed, trying assign:', e);
            window.location.assign(redirectUrl);
        }
        
    } catch (error) {
        console.error('❌ Error fetching itinerary:', error);
        console.error('Error details:', error.message);
        console.error('Full error:', error);
        
        let errorMsg = error.message || 'Unknown error occurred';
        if (error.message && error.message.includes('Failed to fetch')) {
            errorMsg = 'Could not connect to the backend server. Please ensure it is running on http://127.0.0.1:5000';
        }
        
        outputDiv.innerHTML = `<div class="text-center p-8 bg-slate-800 rounded-2xl shadow-xl"><h2 class="text-2xl font-bold text-red-500">Failed to Generate Plan</h2><p class="text-gray-400 mt-2">Error: ${errorMsg}</p><p class="text-gray-500 mt-1 text-sm">Please check the browser console (F12) for more details.</p></div>`;
        setLoadingState(false);
    }
});

function setLoadingState(isLoading) {
    if (isLoading) {
        submitButton.disabled = true;
        buttonText.textContent = 'Generating...';
        buttonSpinner.classList.remove('hidden');
        outputDiv.innerHTML = `<div class="text-center p-8 bg-slate-800 rounded-2xl shadow-xl fade-in"><h2 class="text-2xl font-bold">Generating your custom itinerary...</h2><p class="text-gray-400 mt-2">This will just take a moment!</p></div>`;
    } else {
        submitButton.disabled = false;
        buttonText.textContent = 'Browse Trip';
        buttonSpinner.classList.add('hidden');
    }
}

function displayTripPlan(itinerary) {
    let html = `<div class="bg-slate-800 rounded-2xl shadow-xl p-8 fade-in">`;
    html += `<h2 class="text-3xl font-bold text-center text-white mb-4">${itinerary.title}</h2>`;
    if (itinerary.minimum_budget && itinerary.minimum_budget.total_min) {
        const minB = itinerary.minimum_budget;
        const below = itinerary.budget_summary && itinerary.budget_summary.total_budget < minB.total_min;
        html += `<div class="mb-6 p-4 rounded-xl ${below ? 'bg-red-900/40 border border-red-700' : 'bg-green-900/30 border-green-700'}">` +
                `<p class="text-sm ${below ? 'text-red-300' : 'text-green-300'}">` +
                `Minimum estimated budget for ${itinerary.title.split(' ')[2]} trip: <span class="font-bold">₹ ${formatINR(minB.total_min)}</span>. ` +
                `This is a conservative floor (stay + two meals/day + basics). ${below ? 'Your entered budget is below this estimate.' : ''}` +
                `</p></div>`;
    }
    html += `<div class="mb-8 p-6 bg-slate-700 rounded-xl">` +
            `<h3 class="text-xl font-semibold mb-4 text-gray-200">Budget Breakdown</h3>` +
            `<div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">` +
            `<div><p class="text-sm text-gray-400">Accommodation</p><p class="font-bold text-lg text-blue-400">₹ ${formatINR(itinerary.budget_summary.accommodation)}</p></div>` +
            `<div><p class="text-sm text-gray-400">Food</p><p class="font-bold text-lg text-orange-400">₹ ${formatINR(itinerary.budget_summary.food)}</p></div>` +
            `<div><p class="text-sm text-gray-400">Activities</p><p class="font-bold text-lg text-green-400">₹ ${formatINR(itinerary.budget_summary.activities)}</p></div>` +
            `<div><p class="text-sm text-gray-400">Transport</p><p class="font-bold text-lg text-purple-400">₹ ${formatINR(itinerary.budget_summary.transport)}</p></div>` +
            `</div></div>`;
    if (itinerary.activities_fee_estimated) {
        html += `<div class="mb-4 p-4 bg-slate-700 rounded-lg text-sm text-gray-300">Estimated attraction fees total: ₹ ${formatINR(itinerary.activities_fee_estimated)}</div>`;
    }
    if (itinerary.hotel) {
        const h = itinerary.hotel;
        html += `<div class="mb-8 p-6 bg-slate-700 rounded-xl">` +
                `<h3 class="text-xl font-semibold mb-4 text-gray-200">Suggested Stay</h3>` +
                `<div class="flex flex-col md:flex-row md:items-center md:justify-between">` +
                `<div><p class="text-lg font-bold text-white">${h.name}</p><p class="text-gray-400">Area: ${h.area} • Rating: ${h.rating}</p></div>` +
                `<div class="mt-3 md:mt-0 text-right"><p class="text-gray-400">₹ ${formatINR(h.price_per_night)} / night × ${h.nights} nights</p>` +
                `<p class="font-bold text-blue-400">Estimated: ₹ ${formatINR(h.estimated_total)}</p></div></div></div>`;
    }
    
    if (itinerary.daily_plan && itinerary.daily_plan.length > 0) {
        itinerary.daily_plan.forEach((day_plan, index) => {
            html += `<div class="mb-6 fade-in-up" style="animation-delay: ${index * 150}ms;"><h4 class="text-2xl font-bold text-gray-200 mb-4 border-b-2 border-slate-600 pb-2">Day ${day_plan.day}</h4><ul class="space-y-4">`;
            
            if (day_plan.activities && day_plan.activities.length > 0) {
                day_plan.activities.forEach(activity => {
                    const icon = iconMap[activity.type] || iconMap.default;
                    html += `<li class="flex items-start">${icon}<div><p class="font-semibold text-gray-300">${activity.time}</p><p class="text-gray-400">${activity.description}</p></div></li>`;
                });
            } else {
                 html += `<li class="flex items-start">${iconMap.default}<div><p class="font-semibold text-gray-300">Rest Day</p><p class="text-gray-400">No specific activities planned. Enjoy your free time!</p></div></li>`;
            }

            if (day_plan.restaurants && day_plan.restaurants.length) {
                html += `<div class="mt-4 p-4 bg-slate-700 rounded-lg">` +
                        `<p class="font-semibold text-gray-200 mb-2">Food Suggestions (est. ₹ ${formatINR(day_plan.food_cost_estimated || 0)}):</p>` +
                        `<ul class="space-y-2">`;
                day_plan.restaurants.forEach(r => {
                    html += `<li class="flex items-center"><i data-lucide="utensils" class="w-4 h-4 mr-2 text-orange-400"></i>` +
                            `<span class="text-gray-300">${r.name}</span>` +
                            `<span class="text-gray-500 ml-2">(${r.type}, ★ ${r.rating})</span>` +
                            `<span class="text-gray-400 ml-auto">~ ₹ ${formatINR(r.estimated_cost || 0)}</span></li>`;
                });
                html += `</ul></div>`;
            }
            html += `</ul></div>`;
        });
    } else {
         html += `<p class="text-center text-gray-400">No daily activities or hotel found for this budget. Try increasing your budget.</p>`;
    }
    
    html += `</div>`;
    outputDiv.innerHTML = html; // This line replaces the loading spinner with the plan
    
    // --- THIS IS THE FIX ---
    // I have commented out this line, as it is the most likely source of a silent crash.
    // if (window.lucide) lucide.createIcons();
}

function formatINR(value) {
    try { return Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 }); }
    catch { return value; }
}
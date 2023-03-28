document.addEventListener('keydown', function(e) {
	var handled = false;
	if (e.key !== undefined) {
		if((e.key == "Enter" )) handled = true;
	} else if (e.keyCode !== undefined) {
		if((e.keyCode == 13 )) handled = true;
	}
	// if (handled) {
		// var button = document.getElementById('btn_search');
		// button.click()
		// e.preventDefault();
	// }

	if (!addListener){
		var targetNode = document.querySelector('#chatbot > div.wrap.svelte-byatnx');
		var targetNode2 = document.querySelector('#reviewbot > div.wrap.svelte-byatnx');
		targetNode.addEventListener('DOMSubtreeModified', () => {
		  scroll_to_bottom();
		});
		targetNode2.addEventListener('DOMSubtreeModified', () => {
		  scroll_to_bottom();
		});
		addListener = true
	}
})


function scroll_to_bottom(x){
	var chatbot = document.querySelector('#chatbot > div.wrap.svelte-byatnx');
	var reviewbot = document.querySelector('#reviewbot > div.wrap.svelte-byatnx');
    chatbot.scrollTop = chatbot.scrollHeight;
    reviewbot.scrollTop = reviewbot.scrollHeight;
    return x;
};


var addListener = false

// document.addEventListener('DOMContentLoaded', function() {
  // const xpath = "/html/body/gradio-app/div[2]/div[2]/footer/a";
  // const element = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
// });

// window.onload = function() {
  // const xpath = "/html/body/gradio-app/div[2]/div[2]/footer/a";
  // const element = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;

	// element.setAttribute("href", "https://github.com/newfyu/Braindoor");
	// element.textContent = "Developed by lhan & hjuan  💌"
// };

